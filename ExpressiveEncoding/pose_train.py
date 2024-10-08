import os
import sys
import click
import re
import time

from .train import pose_optimization, torch, get_detector, get_face_info,\
                   edict, yaml, load_model, \
                   PoseEdit, logger, stylegan_path, \
                   LossRegisterBase, np, tqdm, \
                   cv2, DEBUG, StyleSpaceDecoder
from GlintCloud.cloud import genTempName

def finetune_pose(
                  training_path: str, 
                  config_path: str,
                  snapshots_path: str,
                  resume_path: str = None,
                  decoder_path: str = None,
                  option_config_path: str = None,
                  images_dir: str = None
                 ):
    config = edict(dict())
    if config_path is not None:
        with open(option_config_path) as f:
            config = edict(yaml.load(f, Loader = yaml.CLoader))

    # parsing config
    threshold = config.get("threshold", 0.01)
    epochs = config.get("epochs", 10)
    length = config.get("length", -1)
    lr = config.get("lr", 1)
    to_resolution = config.get("resolution", 1024)

    os.makedirs(snapshots_path, exist_ok = True)
    pose_folder = os.path.join(snapshots_path, 'param')
    latent_folder = os.path.join(snapshots_path, 'pose')
    
    os.makedirs(latent_folder, exist_ok = True)
    os.makedirs(pose_folder, exist_ok = True)

    writer = None

    #G = load_model(stylegan_path).synthesis
    G = StyleSpaceDecoder(stylegan_path = stylegan_path, to_resolution = to_resolution)
    for p in G.parameters():
        p.requires_grad = False

    G.to("cuda")
    pose_edit = PoseEdit()
    id_path = os.path.join(training_path, "cache.pt")
    gen_file_list, selected_id_image, selected_id_latent, selected_id = torch.load(id_path)
    if decoder_path is not None:
        G.load_state_dict(torch.load(decoder_path), False)
        #data_path = images_dir #os.path.join(images_dir, "data", "smooth")
        #gen_file_list = [os.path.join(data_path, x) for x in sorted(os.listdir(data_path), key = lambda y: int(''.join(re.findall('[0-9]+',y))))]
        #selected_id_image = cv2.cvtColor(cv2.imread(gen_file_list[selected_id]), cv2.COLOR_BGR2RGB)
    
    if selected_id_image.shape[0] != to_resolution:
        selected_id_image = cv2.resize(selected_id_image, (to_resolution, to_resolution))
    with open(os.path.join(config_path, "pose.yaml")) as f:
        config_pose = edict(yaml.load(f, Loader = yaml.CLoader))
    
    class PoseLossRegister(LossRegisterBase):
        def forward(self, x, y, mask):
            x = mask * x
            y = mask * y
            lpips_loss = self.lpips_loss(x,y).mean() * 1.0
            l2_loss = self.l2_loss(x, y).mean() 
    
            return {
                     "l2_loss": l2_loss,
                     "lpips_loss": lpips_loss
                   }
    
    detector = get_detector()
    face_info_from_id = get_face_info(
                                      np.uint8(selected_id_image),
                                      detector
                                     )
    
    pose_loss_register = PoseLossRegister(config_pose)

    pose_loss_register.lpips_loss.set_device("cuda")

    if length == -1:
        length = len(gen_file_list)

    start_idx = 0
    optimized_pose_latents_length = len(os.listdir(os.path.join(latent_folder)))
    if optimized_pose_latents_length > 0:
        start_idx = optimized_pose_latents_length

    start_idx = 0
    end = 5#length

    pbar = tqdm(gen_file_list[start_idx:end])

    for ii, _file in enumerate(pbar):
        if not DEBUG and ii < start_idx:
            logger.info(f"{ii} processed, pass...")
            continue

        if DEBUG:
            from tensorboardX import SummaryWriter
            tensorboard = os.path.join(snapshots_path, "tensorboard", f"{time.time()}", f"{ii + 1}")
            os.makedirs(tensorboard, exist_ok = True)
            writer = SummaryWriter(tensorboard)
        gen_image = cv2.imread(_file)
        assert gen_image is not None, "file not exits, please check."
        gen_image = cv2.cvtColor(gen_image, cv2.COLOR_BGR2RGB)

        ## resize like gen image
        gen_image = cv2.resize(gen_image, tuple(selected_id_image.shape[:2][::-1]))

        face_info_from_gen = get_face_info(gen_image, detector)
        if resume_path is not None:
            if "expressive" in resume_path:
                param = torch.load(os.path.join(resume_path, f'attribute_{ii + 1}.pt'), map_location = "cpu")
                pose_param = param[0]
            else:
                param = torch.load(os.path.join(resume_path, f'{ii + 1}.pt'))
                pose_param = param
        else:
            pose_param = None

        w_with_pose, image_posed, pose_param = pose_optimization(
                           selected_id_latent.detach(),
                           np.uint8(selected_id_image),
                           gen_image,
                           face_info_from_gen,
                           face_info_from_id,
                           G,
                           pose_edit,
                           pose_loss_register, 
                           resume_param = pose_param,
                           writer = writer,
                           lr = lr, 
                           epochs = epochs,
                           threshold = threshold,
                           target_res = to_resolution
                           )
        torch.save(w_with_pose, os.path.join(latent_folder, f"{ii+1}.pt"))       
        torch.save(pose_param, os.path.join(pose_folder, f"{ii+1}.pt"))       

    total_poses = []
    for ii, _file in enumerate(pbar):
        w_with_pose = torch.load(os.path.join(latent_folder, f"{ii+1}.pt"))
        total_poses.append(w_with_pose)
    # all in one.
    torch.save(total_poses, os.path.join(latent_folder, "poses.pt"))       
    




@click.command()
@click.option('--training_path')
@click.option('--config_path')
@click.option('--snapshots_path')
@click.option('--resume_path', default = None)
@click.option('--decoder_path', default = None)
@click.option('--option_config_path', default = None)
@click.option('--images_dir', default = None)
def invoker_pose_train(
                        *args,
                        **kwargs
                      ):
    return finetune_pose(*args, **kwargs)

if __name__ == '__main__':
    invoker_pose_train()
