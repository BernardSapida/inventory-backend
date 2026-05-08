import os
import yaml

DATASET_DIR = 'F:/Bernard/projects/inventory-backend/dataset'

for dataset in os.listdir(DATASET_DIR):
    if dataset == 'combined':
        continue
    dataset_path = os.path.join(DATASET_DIR, dataset)
    if not os.path.isdir(dataset_path):
        continue
    
    yaml_path = os.path.join(dataset_path, 'data.yaml')
    if not os.path.exists(yaml_path):
        continue

    with open(yaml_path, 'r') as f:
        data = yaml.safe_load(f)
    nc = data.get('nc', 0)
    valid_ids = set(range(nc))

    dirty = 0
    for split in ['train', 'valid', 'test']:
        labels_dir = os.path.join(dataset_path, split, 'labels')
        if not os.path.exists(labels_dir):
            continue
        for label_file in os.listdir(labels_dir):
            with open(os.path.join(labels_dir, label_file)) as f:
                for line in f:
                    parts = line.strip().split()
                    if parts and int(parts[0]) not in valid_ids:
                        dirty += 1

    print(f"{dataset}: nc={nc}, dirty_labels={dirty}")