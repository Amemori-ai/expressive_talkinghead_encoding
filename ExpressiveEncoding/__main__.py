import click
from .train import expressive_encoding_pipeline
from .puppet import puppet, puppet_video

@click.command()
@click.option('--pipeline', default = 'train')
@click.option('--path', default = None)
@click.option('--config_path')
@click.option('--save_path')
@click.option('--decoder_path', default = None)
def main(
         pipeline,
         path,
         config_path,
         save_path,
         decoder_path
        ):
    if pipeline == 'train':
        expressive_encoding_pipeline(config_path, save_path, path, decoder_path)
    elif pipeline == 'puppet':
        puppet(config_path, save_path, path)
    elif pipeline == 'puppet_video':
        puppet_video(config_path, save_path, path)

if __name__ == '__main__':
    main()
