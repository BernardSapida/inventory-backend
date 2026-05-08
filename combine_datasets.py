import os
import shutil
import yaml
from pathlib import Path

# ============================================
# CONFIG - edit these
# ============================================
DATASET_DIR = 'F:/Bernard/projects/inventory-backend/dataset'
OUTPUT_DIR = 'F:/Bernard/projects/inventory-backend/dataset/combined'
# ============================================

if __name__ == '__main__':
    print("🔍 Finding datasets...")
    datasets = []
    for item in sorted(os.listdir(DATASET_DIR)):
        full_path = os.path.join(DATASET_DIR, item)
        if item == 'combined' or not os.path.isdir(full_path):
            continue
        yaml_path = os.path.join(full_path, 'data.yaml')
        if os.path.exists(yaml_path):
            datasets.append(full_path)

    print(f"✅ Found {len(datasets)} datasets: {[os.path.basename(d) for d in datasets]}")

    # Collect all unique classes
    all_classes = []
    dataset_classes = {}
    for dataset_path in datasets:
        yaml_path = os.path.join(dataset_path, 'data.yaml')
        with open(yaml_path, 'r') as f:
            data = yaml.safe_load(f)
        classes = [c.lower() for c in data.get('names', [])]
        dataset_classes[dataset_path] = classes
        for cls in classes:
            if cls not in all_classes:
                all_classes.append(cls)

    print(f"\n📦 Combined classes ({len(all_classes)}): {all_classes}")

    # Create output folders
    for split in ['train', 'valid', 'test']:
        os.makedirs(f'{OUTPUT_DIR}/{split}/images', exist_ok=True)
        os.makedirs(f'{OUTPUT_DIR}/{split}/labels', exist_ok=True)

    # Process each dataset
    for dataset_path in datasets:
        dataset_name = os.path.basename(dataset_path)
        classes = dataset_classes[dataset_path]

        # Build class ID map: old → new
        class_id_map = {}
        for old_id, cls_name in enumerate(classes):
            new_id = all_classes.index(cls_name)
            class_id_map[old_id] = new_id

        print(f"\n📂 Processing: {dataset_name}")
        print(f"   Classes: {classes}")
        print(f"   Class mapping: {class_id_map}")

        for split in ['train', 'valid', 'test']:
            src_images = os.path.join(dataset_path, split, 'images')
            src_labels = os.path.join(dataset_path, split, 'labels')
            dst_images = os.path.join(OUTPUT_DIR, split, 'images')
            dst_labels = os.path.join(OUTPUT_DIR, split, 'labels')

            if not os.path.exists(src_images):
                print(f"   ⚠️ {split} not found — skipping")
                continue

            count = 0
            for img_file in os.listdir(src_images):
                # Unique filename per dataset
                new_name = f"{dataset_name}_{img_file}"

                # Copy image
                shutil.copy(
                    os.path.join(src_images, img_file),
                    os.path.join(dst_images, new_name)
                )

                # Remap and copy label
                label_file = Path(img_file).stem + '.txt'
                label_src = os.path.join(src_labels, label_file)

                if os.path.exists(label_src):
                    new_label = f"{dataset_name}_{label_file}"
                    new_label_path = os.path.join(dst_labels, new_label)

                    with open(label_src, 'r') as f:
                        lines = f.readlines()

                    new_lines = []
                    for line in lines:
                        parts = line.strip().split()
                        if parts:
                            old_id = int(parts[0])
                            if old_id in class_id_map:
                                parts[0] = str(class_id_map[old_id])
                                new_lines.append(' '.join(parts) + '\n')
                            else:
                                print(f"   ⚠️ Unknown class {old_id} in {label_file} — skipping")

                    with open(new_label_path, 'w') as f:
                        f.writelines(new_lines)

                count += 1

            print(f"   ✅ {split}: {count} images")

    # Generate data.yaml
    combined_yaml = {
        'train': f'{OUTPUT_DIR}/train/images',
        'val': f'{OUTPUT_DIR}/valid/images',
        'test': f'{OUTPUT_DIR}/test/images',
        'nc': len(all_classes),
        'names': all_classes
    }

    yaml_path = os.path.join(OUTPUT_DIR, 'data.yaml')
    with open(yaml_path, 'w') as f:
        yaml.dump(combined_yaml, f, default_flow_style=False)

    print(f"\n🎉 Done!")
    print(f"📄 data.yaml: {yaml_path}")
    print(f"📦 nc: {len(all_classes)}")
    print(f"🏷️  names: {all_classes}")

    for split in ['train', 'valid', 'test']:
        images_dir = os.path.join(OUTPUT_DIR, split, 'images')
        if os.path.exists(images_dir):
            count = len(os.listdir(images_dir))
            print(f"📊 {split}: {count} images")