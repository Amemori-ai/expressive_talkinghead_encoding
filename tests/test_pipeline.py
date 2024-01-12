import os
import sys
sys.path.insert(0, os.getcwd())
import pytest
import cv2

from ExpressiveEncoding.train import (get_face_info, 
                                      select_id_latent,
                                      pose_optimization,
                                      facial_attribute_optimization,
                                      expressive_encoding_pipeline,
                                      pivot_finetuning
                                     )

@pytest.mark.face_info
def test_face_info():
    from ExpressiveEncoding.train import get_detector
    detector = get_detector()
    image = cv2.imread("tests/face/164.png")
    assert image is not None, "image not exist."
    image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    face_info = get_face_info(image, detector)

    print(face_info)

@pytest.mark.encoder
def test_encoder():
    from ExpressiveEncoding.train import stylegan_path, StyleSpaceDecoder, load_model, torch
    G = load_model(stylegan_path).synthesis
    face_folder = './tests/face'
    gen_path = "./tests/e4e"
    os.makedirs(gen_path, exist_ok = True)
    gen_files, image, latent, selected_id = select_id_latent(face_folder,
                                                G,
                                                gen_path)

    torch.save(latent, os.path.join(gen_path, 'id_latent.pt'))
    print(selected_id)


@pytest.mark.pose
def test_pose():
    from ExpressiveEncoding.train import load_model, torch, get_detector, yaml, edict, stylegan_path
    detector = get_detector()
    G = load_model(stylegan_path).synthesis
    for p in G.parameters():
        p.requires_grad = False
    pose_edit = PoseEdit()

    face_e4e_path = './tests/e4e/0_gen.png' 
    id_latent_path = './tests/e4e/id_latent.pt'
    id_image_path = './tests/e4e/4_gen.png'
    pose_path = "./tests/pose"
    os.makedirs(pose_path, exist_ok = True)
    selected_id_latent = torch.load(id_latent_path)
    selected_id_image = cv2.imread(id_image_path)
    gen_image = cv2.imread(face_e4e_path)
    selected_id_image = cv2.cvtColor(selected_id_image, cv2.COLOR_BGR2RGB)
    gen_image = cv2.cvtColor(gen_image, cv2.COLOR_BGR2RGB)

    face_info_from_id = get_face_info(
                                        selected_id_image,
                                        detector
                                     )

    face_info_from_gen = get_face_info(gen_image, detector)

    with open('./tests/pose.yaml') as f:
        config_pose = edict(yaml.load(f, Loader = yaml.CLoader))

    w_with_pose, image_posed = pose_optimization( \
                                                   selected_id_latent, \
                                                   selected_id_image, \
                                                   gen_image, \
                                                   face_info_from_gen, \
                                                   face_info_from_id, \
                                                   G, \
                                                   pose_edit, \
                                                   config_pose \
                                                 )
    image_posed = cv2.cvtColor(image_posed, cv2.COLOR_RGB2BGR)
    torch.save(w_with_pose, os.path.join(pose_path, 'latent.pt'))
    cv2.imwrite(os.path.join(pose_path, "pose.png"), image_posed * 255.0)

@pytest.mark.facial_attribute
def test_facial_attribute():
    
    from copy import deepcopy
    from ExpressiveEncoding.train import load_model, torch, get_detector, \
                                         yaml, edict, stylegan_path, \
                                         from_tensor, StyleSpaceDecoder, \
                                         LossRegisterBase
    detector = get_detector()
    G = load_model(stylegan_path).synthesis
    ss_decoder = StyleSpaceDecoder(synthesis = deepcopy(G))
    face_e4e_path = './tests/e4e/0_gen.png' 
    id_latent_path = './tests/pose/latent.pt'
    pose_path = "./tests/facial_attribute"
    os.makedirs(pose_path, exist_ok = True)
    id_latent = torch.load(id_latent_path)
    gen_image = cv2.imread(face_e4e_path)
    gen_image = cv2.cvtColor(gen_image, cv2.COLOR_BGR2RGB)
    with open('./tests/facial_attribute.yaml') as f:
        config_facial = edict(yaml.load(f, Loader = yaml.CLoader))
    face_info_from_gen = get_face_info(
                                        gen_image, 
                                        detector
                                      )

    class FacialLossRegister(LossRegisterBase):
        def forward(self, 
                    x, 
                    y,
                    mask,
                    weights_all,
                    weights,
                    x_pre = None,
                    y_pre = None
                   ):
            l2_loss = self.l2(x, y) * weights_all
            lpips_loss = self.lpips(x,y, is_reduce = False) * weights
            fp_loss = self.fp(x, y, mask)    
            inter_frame_loss = torch.zeros_like(lpips_loss)
            id_loss = self.id_loss(x, y) * 0.0
            ret = {
                     "l2_loss": l2_loss,
                     "lpips_loss": lpips_loss,
                     "fp_loss": fp_loss,
                     "id_loss": id_loss,
                   }
            if x_pre is not None and y_pre is not None:
                inter_frame_loss = self.if_loss(
                                                x,
                                                x_pre, 
                                                y,
                                                y_pre,
                                                self.lpips
                                               ) * 2.0 * weights_all
                ret["diff_frame_loss"] = inter_frame_loss

            return ret

    loss_register = FacialLossRegister(config_facial)
    dlatents_all, images_tensor, gt_images_tensor, gammas, image_gen = facial_attribute_optimization( \
                                                                                                     id_latent, \
                                                                                                     gen_image, \
                                                                                                     face_info_from_gen, \
                                                                                                     loss_register, \
                                                                                                     ss_decoder \
                                                                                                    ) 
    cv2.imwrite("./tests/facial.png", image_gen[...,::-1])

@pytest.mark.pti
def test_pti():
    from copy import deepcopy
    from ExpressiveEncoding.train import load_model, torch, yaml, edict, stylegan_path, from_tensor, StyleSpaceDecoder
    from torch.utils.tensorboard import SummaryWriter
    G = load_model(stylegan_path).synthesis
    ss_decoder = StyleSpaceDecoder(synthesis = deepcopy(G))

    face_folder = './tests/face'
    style_latent_path = './tests/pipeline/facial'
    config_path = './tests/pti.yaml'

    snapshots = './tests/pti'
    os.makedirs(snapshots, exist_ok = True)

    with open(config_path) as f:
        config = edict(yaml.load(f, Loader = yaml.CLoader))

    writer = SummaryWriter(f"./tests/pti/tensorboard/")

    latest_decoder_path = pivot_finetuning(face_folder, style_latent_path, \
                                           snapshots, ss_decoder, \
                                           config, \
                                           writer = writer
                                          )

@pytest.mark.validate
def test_validate():

    from copy import deepcopy
    from ExpressiveEncoding.train import load_model, torch, yaml, edict, stylegan_path, from_tensor, StyleSpaceDecoder, validate_video_gen
    G = load_model(stylegan_path).synthesis
    ss_decoder = StyleSpaceDecoder(synthesis = deepcopy(G))
    state_dict_path = './results/exp002/pti/snapshots/200.pth'
    latent_folder = './results/exp002/facial'
    save_path = "./tests/validate.mp4"
    validate_video_gen(save_path, 
                       state_dict_path,
                       latent_folder,
                       ss_decoder,
                       100
                       )

@pytest.mark.pipeline
def test_pipeline():

    save_path = "./tests/pipeline"
    config_path = './tests/'
    expressive_encoding_pipeline(config_path, save_path)

