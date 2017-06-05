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
import tinycss
import operator
import textwrap
import webbrowser
import subprocess
import collections
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
    with open('auth.json') as fh:
        auth = json.load(fh)
except FileNotFoundError:
    with open('auth.json', 'w') as fh:
        json.dump({
            'client_id': 'crgnKAZFz7bAOg',
            'client_secret': '',
            'username': '',
            'password': ''
        }, fh)
        print("Add credentials to auth.json")
        sys.exit(0)

reddit = praw.Reddit(user_agent='fi.atte.emoter (by /u/AtteLynx)', **auth)
sub = reddit.subreddit(CONFIG['sub'])

def file2name(file):
    return os.path.splitext(os.path.basename(file))[0]

def css2names(source):
    css = tinycss.make_parser().parse_stylesheet(source)
    return set(
        token.value[1:]
        for rule in css.rules
        for container in rule.selector if isinstance(container, tinycss.token_data.ContainerToken)
        for token in container.content if token.type == 'STRING'
    )

# resolve configurations
outfiles = collections.defaultdict(dict)
for fname in glob.iglob(CONFIG['input']['images']):
    for pattern, config in GROUP_CONFIG.items():
        if fnmatch.fnmatch(file2name(fname), pattern):
            outfile = config.get('fname', CONFIG['fname'])
            outfiles[outfile][fname] = copy.deepcopy(CONFIG)
            outfiles[outfile][fname].update(config)
            break
    else:
        outfiles[CONFIG['fname']][fname] = copy.deepcopy(CONFIG)

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
outnames = set()
for outfile, infiles in outfiles.items():
    outname = f"{CONFIG['outdir']}/{outfile}.png"
    outnames.add(outname)
    name = file2name(outname)

    if len(infiles) == 1 and list(infiles.values())[0].get('raw', False):
        # raw images; don't resize
        fname, config = list(infiles.items())[0]
        config['outname'] = outname
        shutil.copy(fname, outname)
        with Image.open(fname) as img:
            css += textwrap.dedent(f"""
                a[href="/{name}"] {{
                    float: left;
                    clear: none;
                    display: block;
                    background-image: url(%%{name}%%);
                    width: {img.width}px;
                    height: {img.height}px;
                }}
            """)
    else:
        images = []
        selectors = []
        # resize images
        for fname, config in infiles.items():
            config['outname'] = outname
            img = Image.open(fname)
            if img.height > config['max_height']:
                config['image'] = img.resize((
                    round(img.width * (config['max_height'] / img.height)),
                    config['max_height'],
                ), Image.ANTIALIAS)
                img.close()
                img = None
            else:
                config['image'] = img
            images.append(config['image'])

            selectors.append(f'a[href="/{file2name(fname)}"]')
        selectors = ',\n'.join(selectors)

        # common rule per output image file
        css += textwrap.dedent(f"""
            {selectors} {{
                float: left;
                clear: none;
                display: block;
                background-image: url(%%{name}%%);
            }}
        """)

        # make target image of correct size
        target = Image.new('RGBA', (
            max(config['image'].width for config in infiles.values()),
            sum(CONFIG['margin'] + config['image'].height for config in infiles.values()),
        ), (255, 255, 255, 255))

        # copy images onto target and generate per-emote rules
        y = 0
        for fname, config in infiles.items():
            img = config['image']
            css += textwrap.dedent(f"""
                a[href="/{file2name(fname)}"] {{
                    background-position: 0 -{y}px;
                    width: {img.width}px;
                    height: {img.height}px;
                }}
            """)
            target.paste(img, (0, y))
            y += img.height + CONFIG['margin']

        target.save(outname)

        for img in images:
            img.close()

# write CSS to file
cssfile = f"{CONFIG['outdir']}/style.css"
with open(cssfile, 'w') as fh:
    fh.write(css)

# optimize outputs
minfile = f"{CONFIG['outdir']}/style.min.css"
subprocess.run(['cleancss', '-o', minfile, cssfile], check=True)
subprocess.run(['optipng'] + list(outnames), check=True)

# diff CSS
old_css = sub.stylesheet().stylesheet
with open(minfile) as fh:
    new_css = fh.read()
old_emotes = css2names(old_css)
new_emotes = css2names(new_css)
diff = ' '.join(sorted(
    [f"+{name}" for name in new_emotes - old_emotes] +
    [f"-{name}" for name in old_emotes - new_emotes]
))
print(f"Changes: {diff}")

# upload data to Reddit
for fname in outnames:
    name, ext = os.path.splitext(os.path.basename(fname))
    print(f"Uploading {name}...")
    sub.stylesheet.upload(name, fname)
print("Uploading CSS...")
sub.stylesheet.update(new_css, reason=diff)

# make test post
print("Shitposting...")
post = sub.submit(
    title=str(datetime.datetime.now()),
    selftext=' '.join(sorted(
        '[{text}](/{name})'.format(name=file2name(fname), text='*testing*' if config.get('text', False) else '')
        for infiles in outfiles.values()
        for fname, config in infiles.items()
    ))
)

# open post if graphical, print otherwise
if os.environ.get('DISPLAY'):
	webbrowser.open(post.shortlink)
else
	print(post.shortlink)

