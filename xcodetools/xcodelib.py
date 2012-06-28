#!/usr/bin/python
# -*- coding:utf-8 -*-

'''\
xcodebuild command을 python으로 쉽게 실행시키기 위한 library

* changelog *
- 2011-09-21 init.
- 2011-11-22 add SimpleBuild

'''

__all__ = ['Xcodebuild', 'Lipo', 'SimpleBuild']

import os
import re
import shlex
import shutil
import subprocess
import unittest

def _system(cmds, shell=False):
    if isinstance(cmds,(str, unicode)):
        cmds = shlex.split(cmds)
    print cmds
    p = subprocess.Popen(cmds, shell=shell, stdout=subprocess.PIPE)
    if not p: return (False, None)
    
    p.wait()
    out = p.stdout.read()
    return p.returncode, out


class Xcodebuild:
    ''' xcodebuild.
    
    usage:
    
    m = Xcodebuild(projfile='xxxx.xcodeproj')
    m.setConfiguration('Release')
    m.setArch(['i386','armv7'])
    m.clean()
    m.build()
    
    '''
    def __init__(self, projfile = None, configuration = None, target = None):
        self.sdks = []
        self.sdk = ''
        if not projfile: projfile = ''
        self.projfile = projfile
        self.configuration = configuration
        self.target = target
        self.flags = {'RUN_CLANG_STATIC_ANALYZER':'NO'}
        self.arch = []
        
    def getSdks(self):
        if self.sdks: return self.sdks
        _, msg = _system('xcodebuild -showsdks')
        self.sdks = re.findall(r'-sdk ([0-9a-zA-Z._]*)', msg)
        return self.sdks
    
    def getSdksForIphone(self):
        sdk = self.getSdks()
        return [x for x in sdk if x.startswith('iphone')]
    
    def setBuildDir(self,dir):
        self.flags['BUILD_DIR'] = dir
    
    def setBuildRoot(self,dir):
        self.flags['BUILD_ROOT'] = dir
        
    def setArch(self, arch):
        if isinstance(arch, basestring):
            self.arch = [ arch ]
        else:
            self.arch = arch
    
    def build(self):
        self._doXcodebuild('build')
    
    def clean(self):
        self._doXcodebuild('clean')
    
    def _doXcodebuild(self, cmd):
        cmds = ['xcodebuild']
        if self.configuration:
            cmds.append('-configuration')
            cmds.append(self.configuration)
        if self.projfile:
            cmds.append('-project')
            cmds.append(self.projfile)
        if self.target:
            cmds.append('-target')
            cmds.append(self.target)
        if self.sdk:
            cmds.append('-sdk')
            cmds.append(self.sdk)
        if self.arch:
            for arch in self.arch:
                cmds.append('-arch')
                cmds.append(arch)


        cmds.append(cmd)
        
        if self.flags:
            for k,v in self.flags.iteritems():
                cmds.append('%s=%s' % (k,v))
        
        #print cmds
        subprocess.call(cmds)
    
    def setConfiguration(self, configuration):
        self.configuration = configuration
        
    def setSdk(self,sdk):
        self.sdk = sdk
        
    def getList(self):
        cmds = ['xcodebuild']
        if self.projfile:
            cmds.append('-project')
            cmds.append(self.projfile)
        cmds.append('-list')
        
        _, msg = _system(cmds)
        
        
class Lipo(object):
    ' lipo를 이용해서 fat file을 만드는 함수'
    def __init__(self):
        self.libs = []
        self.flags = {}
       
    def setFlag(self,k,v):
         self.flags[k] = v
        
    def addLib(self,lib):
        self.libs.append(lib)
        
    def create(self,outpath):
        cmds = ['lipo']
        cmds.append('-create')
        cmds.append('-output')
        cmds.append(outpath)
        cmds.extend(self.libs)

        
        if self.flags:
            for k,v in self.flags.iteritems():
                cmds.append('%s=%s' % (k,v))
        ret = subprocess.call(cmds)
        return ret == 0


class LibBuild(object):
    def __init__(self,projfile = None, configuration = None, target = None, libs=None, outdir='__build__'):
        
        if not projfile:
            import glob
            projs = glob.glob('*.xcodeproj')
            if projs:
                projfile = projs[0]

        if os.path.isdir(projfile):
            import glob
            _,projs,_ = os.walk(projfile).next()
            projs = filter( lambda x : x.endswith('.xcodeproj'), projs)

            if projs:
                projfile = os.path.join(projfile,projs[0])

        self.xcodebuild = Xcodebuild(projfile=projfile, configuration=configuration, target=target)
        self.outdir = outdir
        self.libs = libs
        self.outputs = []
        
    def build(self):
        self.cleanup()

        self.xcodebuild.setBuildDir(self.outdir)
        self.xcodebuild.clean()
        self.xcodebuild.build()

        sdk_simulator = sorted(filter(lambda x : 'simulator' in x, self.xcodebuild.getSdksForIphone())).pop()
        self.xcodebuild.setSdk(sdk_simulator)
        self.xcodebuild.setArch(('i386'))
        self.xcodebuild.build()
        self.makeBigLib()
        
    def makeBigLib(self):
        import glob
        self.outputs = []

        if not self.libs:
            _,_,libs = os.walk(os.path.join(self.outdir,'Release-iphoneos')).next()
            self.libs = filter(lambda x : x.endswith('.a'), libs)

        for lib in self.libs:
            lib_os = os.path.join(self.outdir, 'Release-iphoneos', os.path.basename(lib))
            lib_sim = os.path.join(self.outdir, 'Release-iphonesimulator', os.path.basename(lib))
            fat_lib = os.path.join(self.outdir, os.path.basename(lib))

            l = Lipo()
            l.addLib(lib_os)
            l.addLib(lib_sim)
            l.create(fat_lib)
            self.outputs.append(fat_lib)

    def getLibs(self):
        return self.outputs

    def cleanup(self):
        if os.path.exists(self.outdir):
            shutil.rmtree(self.outdir)

        
class XcodeTest(unittest.TestCase):
    def setUp(self):
        path = '/Users/jinni/local/src/core-plot/framework/CorePlot-CocoaTouch.xcodeproj'
        self.xcode = Xcodebuild(path)
         
    def skip_testBuild(self):
        self.xcode.setSdk('iphonesimulator4.3')
        self.xcode.setConfiguration('Release')
        self.xcode.setBuildDir(os.path.expanduser('~/temp/build'))
        self.xcode.clean()
        self.xcode.build()
    
    def testGetList(self):
        self.xcode.getList()
        
if __name__=='__main__':
    unittest.main()
