import os
from configparser import ConfigParser


class AppConfig:
    _configs = ConfigParser()
    _configs.read(
        os.path.abspath(os.path.join(os.path.dirname(__file__), 'config.ini')))

    @classmethod
    def configs(cls):
        return cls._configs


if __name__ == '__main__':
    from unicore.utilities import StringConsts

    print(AppConfig.configs()[StringConsts.DATABASE])
    print(AppConfig.configs()[StringConsts.DATABASE][StringConsts.DB_URL])
