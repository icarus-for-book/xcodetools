#!/usr/bin/python
# -*- coding:utf-8 -*-

'''\
Convert Images
===============

iOS 앱을 위한 이미지를 만들기.

사용방법
-------

> python convertImages.py -o OUT_DIR icon_big.png

애플은 사용되는 아이콘들이 다르면 앱 등록을 거부하기도 
한다. 따라서 모두 같은 이미지를 사용해서 파일을 만들어야
한다. 

icon_big.png는 512x512이상의 크기를 가지고 있는 이미지를 
권장한다. 이 프로그램을 주어진 이미지를 가지고 사이즈를 
조정하는 기능을 수행한다. 

-o 옵션은 만들어질 파일의 경로를 지정한다. 없으면 파일과
같은 경로에 파일들을 생성한다.

의존라이브러리
-----------

이 프로그램은 이미지 라이브러리인 PIL을 사용하고 있다. 
따라서 이 프로그램을 설치해야 한다. easy_install을 
이용하면 간단히 설치할 수 있다.

> sudo easy_install pil



iOS에서 쓰이는 이미지들
---------------------


Name			Size (pixels)		Platform
---------------------   ---------------------   ----------------------
Icon.png		57 x 57			Universial application icon
Icon-Small.png		29 x 29			Universial application icon for settings area
Icon-72.png		72 x 72			iPad application icon. Alternative name:
Icon-Small-50.png	50 x 50			iPad icon for spotlight search. 
iTunesArtwork		512 x 512		Universial application icon for iTunes App Store. 
Default.png		320 (w) x 480 (h)	iPhone/iPod 2, 3 portrait launch image
Default@2x.png		640 (w) x 960 (h)	iPhone 4 hi-res portrait launch image
Default~ipad.png	768 (w) x 1024 (h)	iPad. Specifies the default portrait launch image. 
Icon@2x.png		114 x 114		iPhone 4 hi-res application icon
Icon-Small@2x.png	58 x 58			iPhone 4 hi-res application icon for settings/search area
Icon-doc.png		22 (w) x 29 (h)		Universial document icon
Icon-doc@2x.png		44 (w) x 58 (h)		iPhone 4 hi-res document icon
Icon-doc~ipad.png	64 x 64			iPad document icon (small)
Icon-doc320~ipad.png	320 x 320		iPad document icon (large)
Default-PortraitUpsideDown~ipad.png	768 (w) x 1024 (h)	iPad. Specifies an upside-down portrait version of the launch image. 
Default-LandscapeLeft~ipad.png		1024 (w) x 768 (h)	iPad. Specifies a left-oriented landscape version of the launch image.
Default-LandscapeRight~ipad.png		1024 (w) x 768 (h)	iPad. Specifies a right-oriented landscape version of the launch image.
Default-Portrait~ipad.png		768 (w) x 1024 (h)	iPad. Specifies the generic portrait version of the launch image. 
Default-Landscape~ipad.png		1024 (w) x 768 (h)	iPad. Specifies the generic landscape version of the launch image. 


reference : http://www.weston-fl.com/blog/?p=840/

'''

import sys
import os
import subprocess
import shlex
import getopt
try:
    import Image
except:
    print '''\
This program need PIL module.

please install PIL module
'''
    exit(1)

# turn on debug mode if you debug
debugmode = False

class ImageConvert:
    def resize(self, src, x, y, dst):

        im = Image.open(src)
        im = im.resize((x,y), Image.ANTIALIAS)
        im.save(dst,'PNG')

def make_artwork_image(srcimg,outdir=os.path.curdir):
    convert = ImageConvert()
    convert.resize(srcimg,512,512,os.path.join(outdir,'iTunesArtwork'))

def make_3gs_images(srcimg,outdir=os.path.curdir):
    convert = ImageConvert()
    convert.resize(srcimg,57,57,os.path.join(outdir,'Icon.png'))
    convert.resize(srcimg,29,29,os.path.join(outdir,'Icon-Small.png'))

def make_4g_images(srcimg,outdir=os.path.curdir):
    convert = ImageConvert()
    convert.resize(srcimg,114,114,os.path.join(outdir,'Icon@2x.png'))
    convert.resize(srcimg,29,29,os.path.join(outdir,'Icon-Small@2x.png'))

def make_ipad_images(srcimg,outdir=os.path.curdir):
    convert = ImageConvert()
    convert.resize(srcimg,72,72,os.path.join(outdir,'Icon-72.png'))
    convert.resize(srcimg,50,50,os.path.join(outdir,'Icon-Small-50.png'))

def make_ipad3_images(srcimg,outdir=os.path.curdir):
    convert = ImageConvert()
    convert.resize(srcimg,144,144,os.path.join(outdir,'Icon-72@2x.png'))
    convert.resize(srcimg,100,100,os.path.join(outdir,'Icon-Small-50@2x.png'))



def usage_and_exit(status):
    print '''\
usage: convertImages.py [option] <input file>

options:
  -o <dir>      set output directory (default : current directory )
  --noartwork     doesn't generate artwork image
  --no3gs         doesn't generate images for 3gs 
  --no4g          doesn't generate images for 4g  
  --noipad        doesn't generate images for ipad 

'''
    exit(status)
    

def main(argv):

    try:
        opts, args = getopt.getopt(argv,'o:',['--no3gs','--no4g','--noipad'])
    except getopt.GetoptError,err:
        print err
        usage_and_exit(1)

    if len(args) != 1:
        usage_and_exit(2)
        
    gen_ipad3 = True
    gen_3gs = True
    gen_4g = True
    gen_ipad = True
    gen_artwork = True
    output = os.path.curdir
    srcimg = args[0]

    for k,v in opts:
        if k == '-o':
            output = v
        elif k == '--no3gs':
            gen_3gs = False
        elif k == '--no4g':
            gen_4g = False
        elif k == '--noipad':
            gen_ipad = False
        elif k == '--noartwork':
            gen_artwork = False

    try:
        if not os.path.exists(output):
            os.makedirs(output)
    except:
        print 'cannot make directory : "%s" ' % output
        exit(3)


    if gen_3gs:
        make_3gs_images(srcimg, outdir=output)
    if gen_4g:
        make_4g_images(srcimg, outdir=output)
    if gen_ipad:
        make_ipad_images(srcimg, outdir=output)
    if gen_artwork:
        make_artwork_image(srcimg, outdir=output)
    if gen_ipad3:
        make_ipad3_images(srcimg, outdir=output)

if __name__=='__main__':
    main(sys.argv[1:])


