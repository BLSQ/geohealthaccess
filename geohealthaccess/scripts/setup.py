"""Generate default files."""

import argparse
import os
from pkg_resources import resource_filename
import shutil

from geohealthaccess.config import load_config


def default_config(dst_dir):
    """Copy default config file."""
    os.makedirs(dst_dir, exist_ok=True)
    config_file = resource_filename(__name__, 'resources/config.ini')
    dst_filename = os.path.join(dst_dir, 'config.ini')
    shutil.copyfile(config_file, dst_filename)
    print(dst_filename)
    return


def default_speeds(dst_dir):
    """Copy default speeds."""
    os.makedirs(dst_dir, exist_ok=True)
    for filename in ('road-network.json', 'land-cover.json'):
        src_filename = resource_filename(__name__, f'resources/{filename}')
        dst_filename = os.path.join(dst_dir, filename)
        shutil.copyfile(src_filename, dst_filename)
        print(dst_filename)
    return


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('project_dir',
                        type=str,
                        help='project directory')
    args = parser.parse_args()
    os.makedirs(args.project_dir, exist_ok=True)
    default_config(args.project_dir)
    default_speeds(os.path.join(args.project_dir, 'data', 'input'))
    print('Done.')
    return


if __name__ == '__main__':
    main()
