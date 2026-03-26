import os
import yaml

def load_config(config_file):
    with open(config_file, encoding='utf-8') as f:
        config = yaml.safe_load(f)
    return config

# Path to the directory containing this file
base_path = os.path.dirname(os.path.abspath(__file__))
config_dir = os.path.join(os.path.dirname(base_path), 'config')

class Cfg(dict):
    def __init__(self, config_dict):
        super(Cfg, self).__init__(**config_dict)
        self.__dict__ = self

    @staticmethod
    def load_config_from_file(fname, base_file=os.path.join(config_dir, 'base.yml')):
        base_config = load_config(base_file)
        with open(fname, encoding='utf-8') as f:
            config = yaml.safe_load(f)
        base_config.update(config)
        return Cfg(base_config)

    @staticmethod
    def load_config_from_name(name, base_file=os.path.join(config_dir, 'base.yml')):
        # Map name like 'vgg_seq2seq' to 'vgg-seq2seq.yml'
        fname = os.path.join(config_dir, name.replace('_', '-') + '.yml')
        return Cfg.load_config_from_file(fname, base_file)

    def save(self, fname):
        with open(fname, 'w') as outfile:
            yaml.dump(dict(self), outfile, default_flow_style=False, allow_unicode=True)
