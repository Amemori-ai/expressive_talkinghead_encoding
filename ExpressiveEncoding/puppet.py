import os
import cv2
import torch
import yaml
import click
import imageio
import numpy as np

from tqdm import tqdm
from easydict import EasyDict as edict
from typing import Callable, List
from functools import reduce
from DeepLog import logger, Timer
from DeepLog.logger import logging

from .encoder import Encoder4EditingWrapper
from .decoder import StyleSpaceDecoder
from .FaceToolsBox.crop_image import crop, crop_one_image

from .train import pivot_finetuning, stylegan_path, e4e_path, \
                   to_tensor, from_tensor, validate_video_gen,\
                   alphas, PoseEdit, get_detector, \
                   get_face_info, DEBUG

def update_alpha(dlatents, alpha_tensor):
    dlatents_tmp = [dlatent.clone() for dlatent in dlatents]
    count = 0
    # first 5 elements.
    for k, v in alphas:
        for i in v:
            dlatents_tmp[k][:, i] = dlatents[k][:, i] + alpha_tensor[count]
            count += 1
    return dlatents_tmp

def puppet(
            config_path,
            save_path
          ):

    import shutil

    config_path = os.path.join(config_path, "config.yaml")

    with open(config_path) as f:
        config = edict(yaml.load(f, Loader = yaml.CLoader))

    puppet_image_path = config.image_path
    driving_latents_folder = config.latent_path
    face_folder_path = config.video_image_path

    writer = None
    if DEBUG:
        from torch.utils.tensorboard import SummaryWriter
        tensorboard_path = os.path.join(save_path, "tensorboard")
        writer = SummaryWriter(tensorboard_path)
    ss_decoder = StyleSpaceDecoder(stylegan_path = stylegan_path)
    e4e = Encoder4EditingWrapper(e4e_path)
    pose_edit = PoseEdit()

    image_puppet = cv2.imread(puppet_image_path)
    assert image_puppet is not None, "image puppet path not exits."

    image_puppet = cv2.cvtColor(image_puppet, cv2.COLOR_BGR2RGB)
    image_puppet = crop_one_image(image_puppet)

    puppet_crop_path = os.path.join(save_path, 'image')
    os.makedirs(puppet_crop_path, exist_ok = True)
    image_puppet_copy = image_puppet.copy()
    cv2.imwrite(os.path.join(puppet_crop_path, '1.jpg'), image_puppet_copy[...,::-1])

    detector = get_detector()
    face_info_from_puppet = get_face_info(image_puppet, detector)

    image_puppet = cv2.resize(image_puppet, (256,256)) / 255.0
    tensor_puppet = (to_tensor(image_puppet).to("cuda") - 0.5) * 2

    with torch.no_grad():
        w_plus_latent = e4e(tensor_puppet)

    # get attribute list.
    attr_files = sorted(os.listdir(driving_latents_folder), key = lambda x: int(x.split('.')[0].split('_')[-1]))

    assert len(attr_files), "attribute file not exits."

    pitch = face_info_from_puppet.pitch
    yaw = face_info_from_puppet.yaw

    with torch.no_grad():
        zflow = pose_edit(w_plus_latent, yaw, pitch)
    
    latent_path = os.path.join(save_path, "latent")
    os.makedirs(latent_path, exist_ok = True)

    for index, attr_file in enumerate(attr_files):
        attr_file = os.path.join(driving_latents_folder, attr_file)
        attr_latents = torch.load(attr_file)
        yaw, pitch = attr_latents[0]
        with torch.no_grad():
            w_plus_with_pose = pose_edit(zflow, yaw, pitch, True)

        style_space_latent = ss_decoder.get_style_space(w_plus_with_pose)
        style_space_with_attr = update_alpha(style_space_latent, attr_latents[1])
        torch.save(style_space_with_attr, os.path.join(latent_path, f'{index + 1}.pt'))
        
    latent_to_train_path = os.path.join(save_path, "latent_to_training")
    os.makedirs(latent_to_train_path, exist_ok = True)


    style_space_latent = ss_decoder.get_style_space(w_plus_latent)
    torch.save(style_space_latent, os.path.join(latent_to_train_path, '1.pt'))

    snapshots_path = os.path.join(save_path, "snapshots")
    os.makedirs(snapshots_path, exist_ok = True)

    pti_config = config.pti
    snapshot_files = os.listdir(snapshots_path)
    if os.path.exists(snapshots_path) and len(snapshot_files):
        snapshot_paths = sorted(snapshot_files, key = lambda x: int(x.split('.')[0]))
        latest_decoder_path = os.path.join(snapshots_path, snapshot_paths[-1])
    else:
        latest_decoder_path = pivot_finetuning(
                                               puppet_crop_path,
                                               latent_to_train_path,
                                               snapshots_path,
                                               ss_decoder,
                                               pti_config,
                                               batchsize = 1,
                                               writer = writer,
                                               epochs = 5000
                                             )

    validate_video_path = os.path.join(save_path, "validate_video.mp4")
    validate_video_gen(
                        validate_video_path,
                        latest_decoder_path,
                        latent_path,
                        ss_decoder,
                        -1,
                        face_folder_path
                      )
    logger.info(f"validate video located in {validate_video_path}")









