#!/usr/bin/env python3
import copy
import glob
import os
import json
import praw
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

reddit = praw.Reddit(user_agent='fi.atte.emoter (by /u/AtteLynx)')
with open('oauth.json') as fh:
	reddit.set_oauth_app_info(**json.load(fh))

print(reddit.get_authorize_url('fi.atte.emoter', 'modconfig modposts submit', True))

for group, images in groups.items():
	config = copy.deepcopy(CONFIG)
	if group:
		config.update(GROUP_CONFIG[group])
