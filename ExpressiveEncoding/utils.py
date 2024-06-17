import os
import torch

from PIL import Image

IMG_EXTENSIONS = [
    '.jpg', '.JPG', '.jpeg', '.JPEG',
    '.png', '.PNG', '.ppm', '.PPM', '.bmp', '.BMP', '.tiff'
]


def is_image_file(filename):
    return any(filename.endswith(extension) for extension in IMG_EXTENSIONS)



def make_dataset(dir):
    images = []
    assert os.path.isdir(dir), '%s is not a valid directory' % dir
    for root, _, fnames in sorted(os.walk(dir)):
        for fname in fnames:
            if is_image_file(fname):
                path = os.path.join(root, fname)
                fname = fname.split('.')[0]
                images.append((fname, path))
    return images

def to_tensor(x):
    return torch.from_numpy(x).permute((2,0,1)).unsqueeze(0).to(torch.float32)

def from_tensor(x):
    return x.detach().squeeze().permute((1,2,0)).cpu().numpy()
