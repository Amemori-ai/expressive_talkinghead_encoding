set -e
bash_script=`dirname ${0}`
exp_name=`echo $bash_script | awk -F '/' '{print $NF}'`
echo $exp_name
username=`whoami` 

mkdir -p results

function main
{ 
  DEBUG=True \
  CUDA_VISIBLE_DEVICES=7 python -m ExpressiveEncoding.pose_train \
                         --training_path ./results/exp010/0/ \
                         --config_path ./scripts/${exp_name} \
                         --snapshots_path ./results/${exp_name} \
                         --resume_path ./results/pose_finetuning_014/param \
                         --decoder_path ./results/pivot_004/snapshots/243.pth \
                         --option_config_path ./scripts/${exp_name}/config.yaml
}

main
