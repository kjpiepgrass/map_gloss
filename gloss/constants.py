#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import re
import string

from utils.IOutils import find_path


__author__ = 'MichaelLockwood'
__email__ = 'lockwm@uw.edu'
__github__ = 'mlockwood'


CLASSIFIERS = {'knn': True, 'maxent': True, 'nb': True, 'tbl': True}
DATASET_FILE = '{}/example/data/dataset.json'.format(find_path('map_gloss'))
DEFAULT_TRAINING = ['dev1', 'dev2', 'test']
MODEL_FILE = '{}/example/data/model.json'.format(find_path('map_gloss'))
OUT_PATH = '{}/example'.format(find_path('map_gloss'))
PUNCTEX = re.compile('[%s]' % string.punctuation)
