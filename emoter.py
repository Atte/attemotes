#!/usr/bin/env python3
import copy
import glob
import os
import json
import fnmatch
from PIL import Image

with open('config.json') as fh:
	CONFIG = json.load(fh)
GROUP_CONFIG = CONFIG.pop('groups')

groups = {}

for fname in glob.iglob(CONFIG['images']):
	for pattern in GROUP_CONFIG.keys():
		if fnmatch.fnmatch(os.path.basename(fname), pattern):
			groups.setdefault(pattern, set()).add(fname)
			break
	else:
		groups.setdefault('', set()).add(fname)

for group, images in groups.items():
	config = copy.deepcopy(CONFIG)
	if group:
		config.update(GROUP_CONFIG[group])
