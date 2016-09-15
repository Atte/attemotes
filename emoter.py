#!/usr/bin/env python3
import os
import sys
import copy
import glob
import json
import praw
import shutil
import fnmatch
import datetime
import operator
import textwrap
import subprocess
from PIL import Image

with open('config.json') as fh:
	CONFIG = json.load(fh)
GROUP_CONFIG = CONFIG.pop('groups')

# check pre-requisites
assert CONFIG['outdir'] and CONFIG['outdir'] != '.'
subprocess.run(['cleancss', '--version'], stdout=subprocess.DEVNULL, check=True)
subprocess.run(['optipng', '--version'], stdout=subprocess.DEVNULL, check=True)

# log in to Reddit (early to allow easy authentication the first time)
try:
	with open('oauth.json') as fh:
		oauth = json.load(fh)
except FileNotFoundError:
	with open('oauth.json', 'w') as fh:
		json.dump({
			'app': {
				'client_id': 'crgnKAZFz7bAOg',
				'client_secret': '',
				'redirect_uri': 'http://127.0.0.1:65010/authorize_callback',
			},
			'code': '',
		}, fh)
		print("Add client_secret to oauth.json")
		sys.exit(0)

reddit = praw.Reddit(user_agent='fi.atte.emoter (by /u/AtteLynx)')
reddit.set_oauth_app_info(**oauth['app'])

if oauth.get('refresh_token'):
	reddit.set_access_credentials(**reddit.refresh_access_information(oauth['refresh_token']))
elif oauth.get('code'):
	access = reddit.get_access_information(oauth['code'])
	oauth['refresh_token'] = access['refresh_token']
	with open('oauth.json', 'w') as fh:
		json.dump(oauth, fh, indent=4)
	print("Token acquired!")
	sys.exit(0)
else:
	print("Add code to oauth.json")
	print(reddit.get_authorize_url('fi.atte.emoter', 'modconfig submit', True))
	sys.exit(0)


def file2name(file):
	return os.path.splitext(os.path.basename(file))[0]

# collect configuration groups
groups = {}
for fname in glob.iglob(CONFIG['input']['images']):
	for pattern in GROUP_CONFIG.keys():
		if fnmatch.fnmatch(file2name(fname), pattern):
			groups.setdefault(pattern, set()).add(fname)
			break
	else:
		groups.setdefault('', set()).add(fname)

# remove old build artifacts
if os.path.exists(CONFIG['outdir']):
	shutil.rmtree(CONFIG['outdir'])
os.mkdir(CONFIG['outdir'])

# load custom CSS
css = ''
for fname in glob.iglob(CONFIG['input']['styles']):
	with open(fname) as fh:
		css += fh.read()

# resize images and generate CSS
emotes = {}
outfiles = set()
for group_i, (group, fnames) in enumerate(groups.items()):
	# merge group config
	config = copy.deepcopy(CONFIG)
	if group:
		config.update(GROUP_CONFIG[group])

	outname = '{outdir}/{fname}.png'.format(outdir=config['outdir'], fname=config['fname'])
	outfiles.add(outname)

	if config.get('raw', False):
		# raw images; don't resize
		assert len(fnames) == 1
		fname = fnames.pop()
		shutil.copy(fname, outname)
		emotes[file2name(outname)] = config
		with Image.open(fname) as img:
			css += textwrap.dedent("""
				a[href="/{name}"] {{
					float: left;
					clear: none;
					display: block;
					background-image: url(%%{name}%%);
					width: {width}px;
					height: {height}px;
				}}
			""").format(name=file2name(outname), width=img.width, height=img.height)
	else:
		images = []
		selectors = []
		# resize images
		for fname in fnames:
			img = Image.open(fname)
			if img.height > config['max_height']:
				images.append(img.resize((
					round(img.width * (config['max_height'] / img.height)),
					config['max_height'],
				), Image.ANTIALIAS))
				img.close()
				img = None
			else:
				images.append(img)

			selectors.append('a[href="/{name}"]'.format(name=file2name(fname)))

		# common rule per output image file
		css += textwrap.dedent("""
			{selectors} {{
				float: left;
				clear: none;
				display: block;
				background-image: url(%%{outname}%%);
			}}
		""").format(selectors=',\n'.join(selectors), outname=file2name(outname))

		# make target image of correct size
		target = Image.new('RGBA', (
			max(img.width for img in images),
			sum(img.height + config['margin'] for img in images),
		), (255, 255, 255, 255))

		# copy images onto target and generate per-emote rules
		y = 0
		for fname, img in zip(fnames, images):
			emotes[file2name(fname)] = config
			css += textwrap.dedent("""
				a[href="/{name}"] {{
					background-position: 0 -{y}px;
					width: {width}px;
					height: {height}px;
				}}
			""").format(
				name=file2name(fname),
				width=img.width,
				height=img.height,
				y=y,
			)

			target.paste(img, (0, y))
			y += img.height + config['margin']

		target.save(outname)

		for img in images:
			img.close()

# write CSS to file
cssfile = '{outdir}/style.css'.format(outdir=CONFIG['outdir'])
with open(cssfile, 'w') as fh:
	fh.write(css)

# optimize outputs
minfile = '{outdir}/style.min.css'.format(outdir=CONFIG['outdir'])
subprocess.run(['cleancss', '-o', minfile, cssfile], check=True)
subprocess.run(['optipng'] + list(outfiles), check=True)

# upload data to Reddit
sub = reddit.get_subreddit(CONFIG['sub'])
for fname in outfiles:
	print("Uploading {name}...".format(name=file2name(fname)))
	sub.upload_image(fname)
print("Uploading CSS...")
with open(minfile) as fh:
	sub.set_stylesheet(fh.read())

# make test post
print("Shitposting...")
sub.submit(
	title=str(datetime.datetime.now()),
	text=' '.join(
		'[{text}](/{name})'.format(name=name, text='*testing*' if config.get('text', False) else '')
		for name, config in sorted(emotes.items(), key=operator.itemgetter(0))
	)
)
