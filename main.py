import os
import numpy as np
from glob import glob
import random

# image data
from skimage import io, color, img_as_float
from skimage.exposure import adjust_gamma
#from sklearn.preprocessing import minmax_scale
import SimpleITK as sitk

# Learning
import torch
import torch.nn as nn
from torch.autograd import Variable

from data_loader import Create_Batch
from preprocessing import Preprocessing
from train import training
from validation import validation
from util import init_model 

import time
import argparse

import warnings
warnings.filterwarnings("ignore")

parser = argparse.ArgumentParser()
parser.add_argument("--gpu_idx",type=int,default=0)
parser.add_argument("--n_epoch",type=int,default=100)
parser.add_argument("--patch_size",type=int,default=64)
parser.add_argument("--n_patch",type=int,default=1000000)
parser.add_argument("--batch_size",type=int,default=1024)
parser.add_argument("--root",type=str,default='/mnt/disk1/data/MRI_Data/')
parser.add_argument("--data_name",type=str,default='MICCAI2008')
parser.add_argument("--n_class",type=int,default=2)
parser.add_argument("--n_mode",type=int,default=4)
parser.add_argument("--volume_size",type=int,default=512)
parser.add_argument("--learning_rate",type=float,default=0.0002)
parser.add_argument("--tr_dim",type=int,default=2)
args = parser.parse_args()

use_gpu = '{},{}'.format(args.gpu_idx,args.gpu_idx+1)
os.environ["CUDA_VISIBLE_DEVICES"]=use_gpu

n_channel = 1
out_dim = 2

n4b = False # Whether to use or not N4 bias correction image
n4b_apply = False # Perform N4 bias correction (if not is_exist corrected image: do this)


# Init models
models, model_idx, model_path = init_model(args)

# Preprocessing
pp = Preprocessing(args, n4b, n4b_apply)
p_path, all_len = pp.preprocess()

# Init optimizer, loss function
optimizer = torch.optim.Adam(models[2].parameters(), lr=args.learning_rate) # classifier optimizer
loss_func = nn.BCEWithLogitsLoss()

# Create data batch
tr_bc = Create_Batch(args.batch_size, int(args.patch_size/2), args.n_mode-1, p_path+'/train')
tr_batch = tr_bc.db_load()

val_path = glob(p_path+'/validation/**')
val_batch = []
for path in val_path:
    val_bc = Create_Batch(args.batch_size, int(args.patch_size/2), args.n_mode-1, path)
    val_batch.append(val_bc.db_load())

# Training start...
cnt = 1
for ep in range(args.n_epoch):

    # Training
    models, cnt, model_idx = training(args, tr_batch, models, loss_func, optimizer, cnt, model_idx, model_path)

    # Validation
    for b in val_batch:
        validation(args, b, models, ep)
