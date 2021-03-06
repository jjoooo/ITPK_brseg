import os
import numpy as np
from glob import glob
import random

# image data
from skimage import io
import SimpleITK as sitk

from ops.patch_extraction import MakePatches

import warnings
warnings.filterwarnings("ignore")
    

# Preprocessing
class Preprocessing(object):

    def __init__(self, args, n4, n4_apply):
        self.args = args
        self.n4bias = n4
        self.n4bias_apply = n4_apply
        self.train_bool = True # Default training
        self.data_name = args.data_name 
        self.root_path = args.root + args.data_name

        self.path = ''
        self.ext = ''

        if self.data_name == 'YS':
            self.path = self.root_path + '/MS'
            self.ext = '.dcm'
            self.patients = glob(self.path + '/**')
            self.volume_depth = len(glob(self.patients[0]+'/*.dcm'))
            if self.args.n_mode==2 and self.n4bias: self.args.n_mode = 3
            
        else:
            self.path = self.root_path + '/training'
            self.ext = '.nhdr'
            self.patients = glob(self.path + '/**')
            if self.args.n_mode==2 and self.n4bias: self.args.n_mode = 3
            self.volume_depth =  args.volume_size
        self.slices_by_mode = np.zeros((self.args.n_mode, self.volume_depth, args.volume_size, args.volume_size))
 

    def _normalize(self, slice):
        # remove outlier
        if self.data_name != 'YS':
            b, t = np.percentile(slice, (1,99))
            slice = np.clip(slice, 0, t)
        slice[slice<0] = 0
        if np.std(slice) == 0: 
            return slice
        else:
            # zero mean norm
            return (slice - np.mean(slice)) / np.std(slice)

    def norm_slices(self, idx, train_bl):
        print('         -> Normalizing slices...')
        if self.data_name != 'YS':
            normed_slices = np.zeros((self.args.n_mode, self.volume_depth, self.args.volume_size, self.args.volume_size))
        else:
            normed_slices = np.zeros((self.args.n_mode-1, self.volume_depth, self.args.volume_size, self.args.volume_size))

        for slice_ix in range(self.volume_depth):
            if self.data_name != 'YS':
                normed_slices[-1][slice_ix] = self.slices_by_mode[-1][slice_ix]

                for mode_ix in range(self.args.n_mode-1):
                    normed_slices[mode_ix][slice_ix] =  self._normalize(self.slices_by_mode[mode_ix][slice_ix])
                    if np.max(normed_slices[mode_ix][slice_ix]) != 0: # set values < 1
                        normed_slices[mode_ix][slice_ix] /= np.max(normed_slices[mode_ix][slice_ix])
                    if np.min(normed_slices[mode_ix][slice_ix]) <= -1: # set values > -1
                        normed_slices[mode_ix][slice_ix] /= abs(np.min(normed_slices[mode_ix][slice_ix]))
                        
            else:
                mask = self.slices_by_mode[-1][slice_ix]

                for mode_ix in range(self.args.n_mode-1):
                    normed_slices[mode_ix][slice_ix] =  self._normalize(self.slices_by_mode[mode_ix][slice_ix])
                    if np.max(normed_slices[mode_ix][slice_ix]) != 0: # set values < 1
                        normed_slices[mode_ix][slice_ix] /= np.max(normed_slices[mode_ix][slice_ix])
                    if np.min(normed_slices[mode_ix][slice_ix]) <= -1: # set values > -1
                        normed_slices[mode_ix][slice_ix] /= abs(np.min(normed_slices[mode_ix][slice_ix]))
                    
                    # Skull stripping
                    normed_slices[mode_ix][slice_ix][mask<1] = 0

                    o_path = self.root_path+'/test_origin_PNG/{}'.format(idx)
                    if not os.path.exists(o_path):
                        os.makedirs(o_path)
                    io.imsave(o_path+'/{}_origin.PNG'.format(slice_ix), normed_slices[mode_ix][slice_ix])
                    if mode_ix == 1:
                        io.imsave(o_path+'/{}_origin_N4.PNG'.format(slice_ix), normed_slices[mode_ix][slice_ix])

            if False: # if need to save 'label, origin img'
                l_path = self.root_path+'/test_label_PNG/{}'.format(idx)
                o_path = self.root_path+'/test_origin_PNG/{}'.format(idx)
                if not os.path.exists(l_path):
                    os.makedirs(l_path)
                if not os.path.exists(o_path):
                    os.makedirs(o_path)
                io.imsave(l_path+'/{}_label.PNG'.format(slice_ix), normed_slices[-1][slice_ix])
                io.imsave(o_path+'/{}_origin.PNG'.format(slice_ix), normed_slices[0][slice_ix])
                io.imsave(o_path+'/{}_origin_N4.PNG'.format(slice_ix), normed_slices[1][slice_ix])

        print('         -> Done.')
        return normed_slices

    def path_glob(self, data_name, path):
        if data_name == 'MICCAI2008':
            flair = glob(path + '/*FLAIR' + self.ext)
            t1 = glob(path + '/*T1' + self.ext)
            t1_n4 = glob(path + '/*T1*_n.mha')
            t2 = glob(path + '/*T2' + self.ext)
            gt = glob(path + '/*lesion' + self.ext)

        elif data_name == 'BRATS2015':
            flair = glob(path + '/*Flair*/*' + self.ext)
            t1 = glob(path + '/*T1*/*' + self.ext)
            t1_n4 = glob(path + '/*T1*/*_n.mha')
            t2 = glob(path + '/*_T2*/*' + self.ext)
            gt = glob(path + '/*OT*/*' + self.ext)

        else:
            flair=[]; t1=[]; t1_n4=[]; t2=[]; gt=[];
            for i in range(11):
                img = glob(path + '/{}.dcm'.format(i))
                mask = glob(path + '/{}_mask.*'.format(i))
                t1.append(img[0])
                gt.append(mask[0])
                
            if glob(path + '/0__n.mha'):
                img_n = glob(path + '/0__n.mha')
                t1_n4.append(img_n[0])

        return flair, t1, t1_n4, t2, gt

    def volume2slices(self, patient):
        print('         -> Loading scans...')

        mode = []
        # directories to each protocol (5 total)
        flair, t1s, t1_n4, t2, gt = self.path_glob(self.data_name, patient)
        t1 = [scan for scan in t1s if scan not in t1_n4]
        
        if self.args.data_name == 'YS':
        
            if self.n4bias:
                if self.n4bias_apply:
                    vol = np.zeros([len(t1), self.args.volume_size, self.args.volume_size])
                    for idx, im_path in enumerate(t1):
                        im = io.imread(im_path,plugin='simpleitk').astype(float)
                        vol[idx] = im
                    
                    vol = sitk.GetImageFromArray(vol)
                    sitk.WriteImage(vol, patient+'/0.mha')
                    self.n4itk_norm(patient+'/0.mha') # n4 normalize
                flair, t1s, t1_n4, t2, gt = self.path_glob(self.data_name, patient)
                mode = [t1[0], t1_n4[0], gt[0]]
            else:
                mode = [t1, gt]

                for mode_idx in range(len(mode)):
                    for slx in range(self.volume_depth):
                        img = io.imread(mode[mode_idx][slx], plugin='simpleitk').astype(float)
                        if mode_idx==0: img = img[0]
                        else: img = img[:,:,0]
                        self.slices_by_mode[mode_idx][slx] = img
            
        else:

            if not self.n4bias:
                if len(t1) > 1:
                    mode = [flair[0], t1[0], t1[1], t2[0], gt[0]]
                else:
                    mode = [flair[0], t1[0], t2[0], gt[0]]
            else:
                if self.n4bias_apply:
                    for im in t1:
                        self.n4itk_norm(im) # n4 normalize

                nm = '/*T1*_n.mha'
                if self.data_name == 'BRATS2015': nm = '/*T1*/'+nm

                t1_n4 = glob(patient + nm)

                if len(t1_n4) > 1:
                    mode = [flair[0], t1_n4[0], t1_n4[1], t2[0], gt[0]]
                else:
                    mode = [flair[0], t1_n4[0], t2[0], gt[0]]

            if self.args.n_mode < 4:
                if self.n4bias:
                    
                    mode = [t1[0], t1_n4[0], gt[0]]
                else:
                    mode = [t1[0], gt[0]]
                
            for mode_idx in range(len(mode)):
                self.slices_by_mode[mode_idx] = io.imread(mode[mode_idx], plugin='simpleitk').astype(float)
    
        print('         -> Done.')

        return True

    def n4itk_norm(self, path):
        img=sitk.ReadImage(path)
        img=sitk.Cast(img, sitk.sitkFloat32)
        img_mask=sitk.BinaryThreshold(img, 0, 0)
        
        print('             -> Applyling bias correction...')
        #corrector = sitk.N4BiasFieldCorrectionImageFilter()
        #corrected_img = corrector.Execute(img, img_mask)
        corrected_img = sitk.N4BiasFieldCorrection(img, img_mask, 0.001, [50,50,30,20])
        print('             -> Done.')
        sitk.WriteImage(corrected_img, path.replace(self.ext, '__n.mha'))

    def save_labels(self, labels):
        for label_idx in range(len(labels)):
            slices = io.imread(labels[label_idx], plugin = 'simpleitk')
            for slice_idx in range(len(slices)):
                io.imsave(self.path[:-3]+'Labels/{}_{}L.png'.format(label_idx, slice_idx), slices[slice_idx])

    def preprocess(self):
        print('\nCreate patches...')
        add_str = ''
        if self.n4bias:
            add_str = '_n4'

        p_path = self.root_path+'/patch/patch_{}'.format(self.args.patch_size)+add_str
        val_str = ''

        if not os.path.exists(p_path):
            os.makedirs(p_path)

        if self.data_name == 'YS':
            if len(glob(p_path+'/test_ys/0/0/**')) > 0:
                print('YS Done.\n')
                return p_path, 0
        else:
            if len(glob(p_path+'/**')) > 1:
                print('MICCAI Done.\n')
                return p_path, 0
        len_patch = 0
        n_val = 1 

        
        for idx, patient in enumerate(self.patients):

            if not self.volume2slices(patient):
                continue
         
            if self.data_name == 'YS':
                self.train_bool = False
                val_str = '/test_ys/{}'.format(idx)
                if not os.path.exists(p_path+val_str):
                    os.makedirs(p_path+val_str)
                if not os.path.exists(p_path+val_str+'/0'):
                    os.makedirs(p_path+val_str+'/0')
                
            else:
                if idx > n_val and idx < n_val+3:
                    self.train_bool = False
                    val_str = '/validation/{}'.format(idx)
                    print(' --> test patch : '+ patient)
                else:
                    self.train_bool = True
                    val_str = '/train'
                    
                for i in range(self.args.n_class):
                    if not os.path.exists(p_path+val_str):
                        os.makedirs(p_path+val_str)
                    if not os.path.exists(p_path+val_str+'/{}'.format(i)):
                        os.makedirs(p_path+val_str+'/{}'.format(i))


            normed_slices = self.norm_slices(idx, self.train_bool)
            # run patch_extraction
            pl = MakePatches(self.args, self.args.n_patch/len(self.patients), self.train_bool)

            if self.data_name == 'YS':
                l_p = pl.create_2Dpatches_YS(normed_slices, p_path+val_str, idx)
                len_patch += l_p
            else: 
                l_p = pl.create_2Dpatches(normed_slices, p_path+val_str, idx)
                len_patch += l_p
            
            print('-----------------------idx = {} & num of patches = {}'.format(idx, l_p))
            
        print('\n\nnum of all patch = {}'.format(len_patch))

        print('Done.\n')
        return p_path, len_patch

    
