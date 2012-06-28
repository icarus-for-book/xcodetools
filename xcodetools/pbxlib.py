#!/usr/bin/python
# -*- coding:utf-8 -*-
r"""pbxlib.py -- a tool to generate and parse pbxproj file

This library can do below.
- parse pxbproj file
- edit pxbproj file

site : 10apps.tistory.com

usage: 
  reference to PbxprojTestCase in this file.



This library use library of jayconrod.com for parsing pbxproj file.
ref : http://www.jayconrod.com/cgi/view_post.py?37
"""

import os
import hashlib
import sys
import re
import copy
import unittest
import operator

__author__ = 'jinsub ahn <jinny831@gmail.com>'

__all__ = ['PbxBuildConfiguration', 'PbxBuildConfigurationList', 'PbxBuildFile', 'PbxBuildPhase', 
           'PbxContainerItemProxy', 'PbxFileReference', 'PbxFrameworksBuildPhase', 'PbxGroup', 
           'PbxHeadersBuildPhase', 'PbxNativeTarget', 'PbxObject', 'PbxProject', 'PbxReferenceProxy', 
           'PbxResourcesBuildPhase', 'PbxSourcesBuildPhase', 'PbxTargetDependency', 'PbxVariantGroup', 
           'PbxVersionGroup', 'Pbxfile', 'PbxprojCache', 'PbxprojParser', 'PbxprojParserExcpetion', 
           'PbxprojTestCase', 'PbxprojWriter']

#
# lexer 
#

RESERVED = 'RESERVED'
STRING   = 'STRING'


#
# token for pbxproj
#
token_exprs = [
    (r'//.*[\n\r]*',    None),
    (r'/\*.*?\*/',      None),
    (r'[ \t\n\r]+',     None),
    (r'{',              RESERVED),
    (r'}',              RESERVED),
    (r'\(',             RESERVED),
    (r'\)',             RESERVED),
    (r',',              RESERVED),
    (r';',              RESERVED),
    (r'=',              RESERVED),
    (r'[a-zA-Z0-9.<>/_]+\b',STRING),
    (r'"([^"\\\r\n]*(?:\\.[^"\\\r\n]*?)*?)"',         STRING),
]

def lex(characters, token_exprs):
    ' lexer '
    pos = 0
    tokens = []
    while pos < len(characters):
        match = None
        for token_expr in token_exprs:
            pattern, tag = token_expr
            regex = re.compile(pattern)
            match = regex.match(characters, pos)
            if match:
                if len(match.groups()) > 0:
                    text = match.group(1)
                else:
                    text = match.group(0)
                if tag:
                    token = (text, tag)
                    if tag:
                        tokens.append(token)
                break
        if not match:
            sys.stderr.write('Illegal character: %s:%s\n' % (characters[pos],characters[pos-10:pos+10]))
            sys.exit(1)
        else:
            pos = match.end(0)
    return tokens

# lexer function pbxproj fil
def pbxlexer(tokens):
    'lexer function for pbxproj file'
    return lex(tokens, token_exprs)

#
# parser
# parsing중에 사용한 class들 정의 
#

class Result:
    'parsing과정에서 만들어지는 결과를 저장할 object'
    def __init__(self, value, pos):
        self.value = value
        self.pos = pos

    def __repr__(self):
        return 'Result(%s, %d)' % (self.value, self.pos)

class Parser:
    '''parser의 최상위 object.
    
    concat ( + ) : 두개의 parser를 합침. 각각의 parser가 만족해야 전체가 만족. 
    exp ( * )    : 1개 이상 같은 parser를 만족 시켜야 하는 parser 생성 
    or  ( | )    : a | b  a 혹은 b parser를 만족시켜야 하는 parser 생성 
    xor ( ^ )    : parser 조건을 만족 시킨 경우 등록된 callable object 실행 시키는 parser 생성.
    
    '''
    def __add__(self, other):
        return Concat(self, other)

    def __mul__(self, other):
        return Exp(self, other)

    def __or__(self, other):
        return Alternate(self, other)

    def __xor__(self, function):
        return Process(self, function)

class Tag(Parser):
    'parsing하려는 token의 type이 주어진 것과 같은 경우에 만족'
    
    def __init__(self, tag):
        self.tag = tag

    def __call__(self, tokens, pos):
        if pos < len(tokens) and tokens[pos][1] is self.tag:
            return Result(tokens[pos][0], pos + 1)
        else:
            return None

class Reserved(Parser):
    'parsing하려는 token이 주어진 keyword인 경우에 만족하는 parser '
    
    def __init__(self, value, tag):
        self.value = value
        self.tag = tag

    def __call__(self, tokens, pos):
        if pos < len(tokens) and \
           tokens[pos][0] == self.value and \
           tokens[pos][1] is self.tag:
            return Result(tokens[pos][0], pos + 1)
        else:
            return None

class String(Parser):
    'parsing 하려는 token이 string인 경우에 만족하는 parser '
    def __init__(self):
        pass
    def __call__(self, tokens, pos):
        if pos < len(tokens) and \
           tokens[pos][1] is STRING:
            return Result(tokens[pos][0], pos + 1)
        else:
            return None

class Concat(Parser):
    '두개의 parser를 모두 만족시켜야 하는 parser.'
    def __init__(self, left, right):
        self.left = left
        self.right = right

    def __call__(self, tokens, pos):
        left_result = self.left(tokens, pos)
        if left_result:
            right_result = self.right(tokens, left_result.pos)
            if right_result:
                combined_value = (left_result.value, right_result.value)
                return Result(combined_value, right_result.pos)
        return None

class Exp(Parser):
    '첫번째 parser간 만족하고 같은 parser가 추가적으로 만족 해야 하는 경우에 만족하는 parser'
    def __init__(self, parser, separator):
        self.parser = parser
        self.separator = separator

    def __call__(self, tokens, pos):
        result = self.parser(tokens, pos)

        def process_next(parsed):
            (sepfunc, right) = parsed
            return sepfunc(result.value, right)
        next_parser = self.separator + self.parser ^ process_next

        next_result = result
        while next_result:
            next_result = next_parser(tokens, result.pos)
            if next_result:
                result = next_result
        return result            

class Alternate(Parser):
    '첫번째 parser 혹은 두번째 parser간 만족하면 만족하는 parser '
    def __init__(self, left, right):
        self.left = left
        self.right = right

    def __call__(self, tokens, pos):
        left_result = self.left(tokens, pos)
        if left_result:
            return left_result
        else:
            right_result = self.right(tokens, pos)
            return right_result

class Process(Parser):
    'parser간 만족하면 주어진 function을 실행시키는 parser '
    def __init__(self, parser, function):
        self.parser = parser
        self.function = function

    def __call__(self, tokens, pos):
        result = self.parser(tokens, pos)
        if result:
            result.value = self.function(result.value)
            return result

class Opt(Parser):
    'parser간 성공 혹은 실패한 경우에도 만족하는 parser '
    def __init__(self, parser):
        self.parser = parser

    def __call__(self, tokens, pos):
        result = self.parser(tokens, pos)
        if result:
            return result
        else:
            return Result(None, pos)
        
class Lazy(Parser):
    'syntex를 정의할때 syntex간의 cycle이 될때의 이를 방지하기 위한 parser'
    def __init__(self, parser_func):
        self.parser = None
        self.parser_func = parser_func

    def __call__(self, tokens, pos):
        if not self.parser:
            self.parser = self.parser_func()
        return self.parser(tokens, pos)

class Phrase(Parser):
    '주어진 token을 모두 사용한 경우에 만족하는 parser '
    def __init__(self, parser):
        self.parser = parser

    def __call__(self, tokens, pos):
        result = self.parser(tokens, pos)
        if result and result.pos == len(tokens):
            return result
        else:
            return None

# Top level parser
def parseForPbxproj(tokens):
    ast = Phrase(stmt())(tokens, 0)
    return ast

# non-terminal parser

def stmt():
    ''' root statement
    
    stmt := dict_stmt | list_stmt 
    '''
    return dict_stmt() | list_stmt()

# Statements
def list_stmt():
    '''
    list_stmt := '(' ')' | '(' object_stmt * ')' | '(' object_stmt * ',' ')' 
    '''
    separator = keyword(',') ^ (lambda x: lambda l, r: l+r)
    def listitem_process(x):
        return (x,) 
    def process_list(parsed):
        ((_,v),_) = parsed
        if v == None: v = ()
        return v
    def process_list2(parsed):
        (((_,v),_),_) = parsed
        return v
    
    return keyword('(') + Opt( Exp(Lazy(object_stmt) ^ listitem_process, separator) ) + keyword(')') ^ process_list |\
           keyword('(') + Exp(Lazy(object_stmt) ^ listitem_process, separator) + keyword(',') + keyword(')') ^ process_list2

def dict_keyval_stmt():
    '''
    dict_keyval_stmt := string '=' object_stmt 
    '''
    def process(parsed):
        ((k,_),v) = parsed
        return (k,v)
    return String() + keyword('=') + Lazy(object_stmt) ^ process


def dict_stmt():
    '''
    dict_stmt := '{' '}' | '{'  dict_keyval_stmt * '}' | '{'  dict_keyval_stmt * ';' '}'  
    '''
    def dict_process(result):
        (((_,l),_),_) = result
        ret = {}
        for i in range(0,len(l),2):
            k = l[i]
            v = l[i+1]
            ret[k] = v
        return ret

    def dict_process2(result):
        ((_,l),_) = result
        ret = {}
        for i in range(0,len(l),2):
            k = l[i]
            v = l[i+1]
            ret[k] = v
        return ret
    
    separator = keyword(';') ^ (lambda x: lambda l,r: l+r)
    parser = keyword('{') + keyword('}') ^ (lambda x: {}) | \
             keyword('{') + Exp(dict_keyval_stmt(), separator) + keyword('}') ^ dict_process2 |\
             keyword('{') + Exp(dict_keyval_stmt(), separator) + keyword(';') + keyword('}') ^ dict_process
               
    return parser

def object_stmt():
    '''
    object_stmt := string | dict_stmt | list_stmt
    '''
    return String() | dict_stmt() | list_stmt()  

# terminal parser
def keyword(kw):
    return Reserved(kw, RESERVED)

def process_print(x):
    'print result for debuging parse toknes'
    print x

class PbxprojParserExcpetion(Exception):
    'exception for parsing'
    pass

    

class PbxprojParser:
    def __init__(self, data):
        self.tokens = lex(data, token_exprs)

    def parse(self):
        return PbxProject( parseForPbxproj(self.tokens).value )
    
    
    
# The following relative path methods recyled from:
# http://code.activestate.com/recipes/208993-compute-relative-path-from-one-directory-to-anothe/
# Author: Cimarron Taylor
# Date: July 6, 2003
def pathsplit(p, rest=[]):
    (h,t) = os.path.split(p)
    if len(h) < 1: return [t]+rest
    if len(t) < 1: return [h]+rest
    return pathsplit(h,[t]+rest)

def commonpath(l1, l2, common=[]):
    if len(l1) < 1: return (common, l1, l2)
    if len(l2) < 1: return (common, l1, l2)
    if l1[0] != l2[0]: return (common, l1, l2)
    return commonpath(l1[1:], l2[1:], common+[l1[0]])

def relpath(p1, p2):
    (common,l1,l2) = commonpath(pathsplit(p1), pathsplit(p2))
    p = []
    if len(l1) > 0:
        p = [ '../' * len(l1) ]
    p = p + l2
    return os.path.join( *p )

class PbxprojWriter:
    '''pbxproj file writer'''
    def __init__(self, fileobj, indentLevel = 0, indent = '\t'):
        self.file = fileobj
        self.stack = []
        self.indentLevel = indentLevel
        self.indent = indent
        self.beginOfLine = True
        self.encoding='utf-8'
        
        self.writeln('// !$*UTF8*$!')
    
    def writeValue(self, value):
        if isinstance(value, (str, unicode)):
            self.writeString(value)
        elif isinstance(value,bool):
            self.writeString(value and 'YES' or 'NO')
        elif isinstance(value,int):
            self.writeString(str(value))
        elif isinstance(value,dict):
            self.writeDict(value)
        elif isinstance(value,(tuple,list)):
            self.writeArray(value)
        else:
            raise TypeError("unsuported type: %s" % type(value))
            
    def writeArray(self, data):
        self.beginElement('(')
        if data:
            self.write('')
            for item in data:
                self.writeValue(item)
                if item != data[-1]:
                    self.writeln(',')
        self.endElement(')')
    
    def writeDict(self, data):
        self.beginElement("{")
        
        if data:
            
            # 한줄로 표시할 data
            oneline = data.get('isa') in ('PBXFileReference','PBXBuildFile' )
             
            if not oneline : self.writeln('')
            
            keys = sorted(data.keys())
            
            # isa를 가지고 있으면 isa에 따라서 키를 정렬 
            # 보기에 안좋아서 정렬하도록함. 
            if type(data[keys[0]]) == dict and data[keys[0]].get('isa'):
                keys.sort(key=lambda x: data[x]['isa'])
                
            # 
            #
                        
            for k in keys:
                v = data[k]
                self.writeValue(k)
                self.write("=")
                self.writeValue(v)
                
                if oneline:
                    self.write(';')
                else: 
                    self.writeln(";")
                
        self.endElement("}")
    
    def writeString(self, data):
        if data and re.match(r'^\w*$', data):
            self.write(data)
        else:
            self.write('"')
            self.write(data)
            self.write('"')
        
    def writeln(self, line):
        if self.beginOfLine and line:
            self.file.write(self.indentLevel * self.indent)
            
        if line:
            self.file.write(line.encode(self.encoding) + "\n")
            self.beginOfLine = True
        else:
            self.file.write("\n")
            self.beginOfLine = True
            
    def write(self, data):
        if self.beginOfLine:
            self.file.write(self.indentLevel * self.indent)

        self.file.write(data.encode(self.encoding))
        self.beginOfLine = False

    def beginElement(self, tag=''):
        self.write(tag)
        self.indentLevel += 1

    def endElement(self,tag=''):
        self.indentLevel -= 1
        self.write(tag)
    

# xcode가 지원하는 filename extension과 type를 나타내는 dictionary    
__bundletypes = {
                 '.png' : 'image.png',
                 '.xib' : 'file.xib',
                 '.h'   : 'sourcecode.c.h',
                 '.pch' : 'sourcecode.c.h',
                 '.m'   : 'sourcecode.c.objc',
                 '.framework' : 'wrapper.framework',
                 '.xcdatamodel': 'wrapper.xcdatamodel',
                 '.xcodeproj': 'wrapper.pb-projec',
                 '.a'   : 'archive.ar'}

def get_bundletype(filename):
    '확장자에 따른 xcode에서의 bundle type 구하기'
    _, ext = os.path.splitext(filename)
    ret = __bundletypes.get(ext)
    if not ret:
        raise Exception('not supported bundle name : %s' % filename )
    return ret

#cache for pbxproj
PbxprojCache = {}

class PbxObject(object):
    'pbxobject의 최상의 object'
    def __init__(self, pbxproj, guid):
        self.pbxproj = pbxproj
        self.pbxdata = pbxproj and pbxproj.pbxdata or None
        self.guid = guid
        self.obj = None
        self.pbxtype = ''
        
        if guid:
            self.obj = self.pbxdata['objects'][guid]
            
    def getRootObject(self):
        return self.pbxdata['objects']
        
    def getGuid(self):
        return self.guid
    
    def getObject(self,guid):
        return self.pbxdata['objects'][guid]
    
    def get(self,key):
        if self.obj.has_key(key):
            return self.obj[key]
        else:
            return None
        
    def set(self,key,val):
        self.obj[key] = val
        
    def appendValue(self, key, aVal):
        value = self.get(key)
        value += (aVal,)
        self.set(key, value)
        assert aVal in self.get(key)
        return True;
    
    def removeValue(self, key, aVal):
        value = self.get(key)
        value = list(value)
        if aVal in value:
            value.remove(aVal)
        self.set(key, tuple(value))
        assert aVal not in self.get(key)
        return True;
    
    def removeObjectFromRoot(self):
        if self.guid:
            del self.pbxdata['objects'][self.guid]
        
    def __eq__(self, other):
        return self.guid and self.guid == other.guid
    
class Pbxfile:
    def __init__(self, path):
        pass
        
class PbxProject(PbxObject):
    'pbxproj file를 조회 수정하기 위한 class.'
    def __init__(self, pbxproj=None, guid=None):
        self.path = None
        self.data = None
        self.name = None
        self.target = None
        self.valid = False
        self.file_basepath = None
        PbxObject.__init__(self, pbxproj, guid)
        
    @staticmethod
    def loadPbxproj(path):
        ' load project file'
        pbxpath = None

        path = os.path.expanduser(path)

        # find project file path
        if os.path.isfile(path): 
            pbxpath = path
        elif os.path.isfile(os.path.join(path,'project.pbxproj')): 
            pbxpath = os.path.join(path,'project.pbxproj')

        if PbxprojCache.has_key(os.path.abspath(pbxpath)):
            return PbxprojCache[os.path.abspath(pbxpath)]
        
        pbx = file(pbxpath).read().decode('utf-8')
        
        tokens = lex(pbx, token_exprs)

        # data parsing
        data = parseForPbxproj(tokens).value
        obj = None
        if data: 
            obj = PbxProject()
            
            obj.pbxproj = obj
            obj.pbxdata = data
            obj.path = pbxpath
            obj.name =  os.path.basename(os.path.dirname(pbxpath))
            obj.target = os.path.splitext(obj.name)[0]
            obj.obj = obj.objectForProject()
            
            PbxprojCache[os.path.abspath(pbxpath)] = obj
            
        return obj
    
    @staticmethod
    def createPbxproj(path):
        'create project file'
        
        data = {'archiveVersion':1,
                'classes':{},
                'objectVersion':'46',
                'rootObject':'43336CFE13D8F58100640656',
                'objects': { 
                            '43336CFE13D8F58100640656' : {
                                                          'isa' : 'PBXProject',
                                                          'buildConfigurationList' : '43336D2813D8F58100640656',
                                                          'compatibilityVersion':'Xcode 3.2',
                                                          'developmentRegion':'English',
                                                          'hasScannedForEncodings' : '0',
                                                          'knownRegions':('en'),
                                                          'mainGroup':'',
                                                          'productRefGroup':'',
                                                          'projectRoot':'',
                                                          'targets':()
                                                          },
                            '43336D2813D8F58100640656' : {
                                                          'isa' : 'XCConfigurationList',
                                                          'buildConfigurations' : (),
                                                          'defaultConfigurationIsVisible' : 0,
                                                          'defaultConfigurationName' : ''
                                                          }
                            }
                
                }

        # find project file path
        pbxpath = path
        if os.path.basename(path) == 'project.pbxproj': 
            pbxpath = path
        elif os.path.basename(path).endswith('.xcproj'):
            if not os.path.exists(path):
                os.makedirs(path, 0755)
            pbxpath = os.path.join(path,'project.pbxproj')
        
        
        obj = PbxProject()
        obj.pbxproj = obj
        obj.pbxdata = data
        obj.path = pbxpath 
        obj.name =  os.path.basename(os.path.dirname(pbxpath))
        obj.target = os.path.splitext(obj.name)[0]
        obj.obj = obj.objectForProject()
            
        return obj
        

            
    #
    # save function
    #
        
    def save(self):
        self.saveas(self.path)

    def saveas(self,path):
        f = file(path,'w')
        writer = PbxprojWriter(f)
        writer.writeValue(self.pbxdata)
        f.close()
        
    #
    # object 조회 
    #
        
    def object_if(self,dic):
        'objects 값 중에서 key와 value를 동일하게 가지고 있는 object를 반환 '
        for k,v in self.pbxdata['objects'].iteritems():
            found = True
            for qk, qv in dic.iteritems():
                if type(v) != dict or not v.has_key(qk) or v[qk] != qv:
                    found = False
            
            if found:
                return k,v
        return None
        
    def objects_if(self,dic):
        'objects 값 중에서 key와 value를 동일하게 가지고 있는 object를 반환 '
        
        ret = []
        
        for k,v in self.getRootObject().iteritems():
            found = True
            for qk, qv in dic.iteritems():
                if type(v) != dict or not v.has_key(qk) or v[qk] != qv:
                    found = False
            
            if found:
                ret.append((k,v))
        return ret

    def xcodeprojpath(self):
        return os.path.dirname(self.path)
    
    def object(self,guid):
        return self.pbxdata['objects'][guid]

    def objects(self):
        return self.pbxdata['objects']
    
    def objectForProject(self):
        projguid = self.pbxdata['rootObject']
        obj= self.pbxdata['objects'][projguid]
        return obj
    
    def getMainGroup(self):
        mainGroup = self.get('mainGroup')
        return createPbxObject(self.pbxproj, mainGroup)

    def __str__(self):
        import pprint
        pp = pprint.PrettyPrinter(indent=4)
        return pp.pformat(self.pbxdata)

    #
    # path function 
    #

    def get_file_base_path(self):
        '''xcode에 file, resource를 추가할때의 path 기준을 구한다.
        
        project의 main group중에 path를 가지고 있는 group의 위치를 기준 path로 본다.
        
        '''
        
        if self.file_basepath: return self.file_basepath

        # main group object 찾기         
        _,maingroupobj = self._get_root_group()
        basepath = os.path.dirname(self.xcodeprojpath())
        
        # main group의 하위 group를 찾아서 path 경로가 있는지 확인 
        for g in maingroupobj['children']:
            aObj = self.pbxdata['objects'][g]
            if aObj.has_key('path') and aObj['isa'] == 'PBXGroup':
                return os.path.join(basepath, aObj['path'])
            
        self.file_basepath = basepath
        return basepath
    
    def getRootPath(self):
        '''project path (.xcproject 파일이 있는 폴더 )'''
        ret = os.path.dirname(self.xcodeprojpath())
        return ret

    def getRelPathFromProjPath(self, path):
        basepath = os.path.dirname(self.xcodeprojpath())
        return os.path.normpath(os.path.relpath(path, basepath))
    
    def getRelPathFromFilePath(self, path):
        basepath = self.get_file_base_path()
        return os.path.normpath(os.path.relpath(basepath, path))
    
    def getAbsPathFromRelProjPath(self,path):
        basepath = os.path.dirname(self.xcodeprojpath())
        return os.path.abspath(os.path.join(basepath, path))
    
    def getAbsPathFromRelFilePath(self,path):
        basepath = self.get_file_base_path()
        return os.path.abspath(os.path.join(basepath, path))

    # deprecated function
    get_relative_file_path = getRelPathFromFilePath
    get_abs_proj_path = getAbsPathFromRelFilePath
    get_relative_proj_path = getRelPathFromProjPath
    
    
    #
    # public function
    #
    def addProject(self, project_path,group=None, dependency=True, link=True):
        assert os.path.exists(project_path)
        
        if not group : group = self.pbxproj.getMainGroup().addGroupFromPath('/Libraries')
        
        filerefs = self.pbxproj.getAllObjects(isa='PBXFileReference', path=project_path)
        
        # get file reference ( local file )
        if not filerefs:
            filerefs = self.pbxproj.getAllObjects(isa='PBXFileReference')
            filerefs = filter(lambda x : x.getAbspath() == project_path, filerefs)
            
        # if exists already.
        if filerefs: return False
            
        # project file reference 추가
        obj = PbxFileReference.createObject(self.pbxproj, project_path)

        # project group 추가 
        group.addFileReference(obj)
        fileref_hash = obj.getGuid()
        
        # contatiner proxy 생성
        containers = self._add_project_proxy(fileref_hash, project_path) 
        
        # project product reference proxy 생성
        proxyrefs = []
        for container in containers:
            proxyrefs.append(self._add_referenceproxy(container[2], container[0]))
        
        # product group에 추가
        if proxyrefs:
            obj = {'isa':'PBXGroup',
                   'children' : proxyrefs,
                   'name':'Products',
                   'sourceTree':'<group>'}
            guid = self.createPbxGuid()
            self.pbxdata['objects'][guid] = obj
            groupguid = guid
            
        # project reference를 project에 등록.
        projobj = self.objectForProject()
        
        if not projobj.has_key('projectReferences'):
            projobj['projectReferences'] = () 
            
        
        projobj['projectReferences'] += ({'ProductGroup' : groupguid,
                                          'ProjectRef'   : fileref_hash},)
        
        if dependency or link:
            otherpbx = PbxProject.loadPbxproj(project_path)
            libname = [x.getProductFileName() for x in otherpbx.getPbxTargets() if x.isLibrary()]
            target = self.getDefaultTarget()
        
            if dependency:
                for i in libname:
                    target.addTargetDependency(i)
            
            if link:
                for i in libname:
                    target.addLibrary(i)

        return True
    
    def removeProject(self, project_path):
        # project file reference 제거
        fileref = self.getAllObjectsWithConditions({'isa':'PBXFileReference','path':self.get_relative_proj_path(project_path)})
        if not fileref: return
        fileref = fileref[0]
        
        # delete file reference 
        filerefguid = fileref.getGuid()
        fileref.removeObjectFromRoot()
    
        proxy_guid = []    
        objs = self.getAllObjectsHasGuid(filerefguid)
        for obj in objs:
            # group
            if isinstance(obj, PbxGroup):
                obj.removeValue('children', filerefguid) 
            # continaer proxy
            elif isinstance(obj, PbxContainerItemProxy):
                proxy_guid.append(obj.getGuid())
                obj.removeObjectFromRoot()
            elif isinstance(obj, PbxProject):
                # remove proejctReferences
                projrefs = obj.get('projectReferences')
                assert projrefs != None
                for projref in projrefs:
                    if projref['ProjectRef'] == filerefguid:
                        #remove product group 
                        g = createPbxObject(self.pbxproj, projref['ProductGroup'])
                        g.removeObjectFromRoot()
                        #remove projectReference
                        obj.removeValue('projectReferences', projref)
                        break
                
            else:
                raise Exception('not support object')

        target_dependencies = []
        reference_proxies = []
        for guid in proxy_guid:
            objs = self.getAllObjectsHasGuid(guid)
            for obj in objs:
                # targetdependency
                if isinstance(obj, PbxTargetDependency):
                    target_dependencies.append(obj.getGuid())
                    obj.removeObjectFromRoot()
                # reference proxy
                elif isinstance(obj, PbxReferenceProxy):
                    reference_proxies.append(obj.getGuid())
                    obj.removeObjectFromRoot()
                else:
                    raise Exception('not support object')
        
        build_files = []
        for guid in target_dependencies + reference_proxies:
            objs = self.getAllObjectsHasGuid(guid)
            for obj in objs:
                # PBXGroupx
                if isinstance(obj, PbxGroup):
                    obj.removeObjectFromRoot()
                # PBXNativeTarget
                elif isinstance(obj, PbxNativeTarget):
                    obj.removeValue('dependencies',guid)
                elif isinstance(obj, PbxBuildFile):
                    build_files.append(obj.getGuid())
                    obj.removeObjectFromRoot()
                else:
                    raise Exception('not support object')
                
        # delete file in FrameworkbuildPhase
        for guid in build_files:
            objs = self.getAllObjectsHasGuid(guid)
            for obj in objs:
                # BuildPhase
                if isinstance(obj, PbxBuildPhase):
                    obj.removeFile(guid)
                else:
                    raise Exception('not support object')
    
    def add_header_search_path(self,configuration, paths):
        
        if type(paths) not in (list,tuple):
            paths = (paths,)
        
        _,obj = self.object_if({'isa':'XCBuildConfiguration','name':configuration})
        if not obj : return False
        
        if obj['buildSettings'].has_key('HEADER_SEARCH_PATHS'):
            obj['buildSettings']['HEADER_SEARCH_PATHS'] += paths 
        else:
            obj['buildSettings']['HEADER_SEARCH_PATHS'] = paths 
    

    #
    # private function
    #

    def _add_buildfile(self, file_ref_hash, guid):
        objs = self.pbxdata['objects']
        objs[guid] = { 'isa' : 'PBXBuildFile',
                               'fileRef' : file_ref_hash }
        return guid 
    
    def _add_filereference(self, name, file_type, guid, rel_path, source_tree):
        obj = self.object_if({'isa':'PBXFileReference','name':name, 'path':rel_path})
        if obj: return obj[0]
        
        self.pbxdata['objects'][guid] = {'isa': 'PBXFileReference',
                                        'lastKnownFileType': file_type,
                                        'name':name,
                                        'path':rel_path,
                                        'sourceTree':source_tree}
        
        return guid
    
    def _get_root_group(self):
        _,obj = self.object_if({'isa':'PBXProject'})
        if not obj : return None
        
        maingroup = self.pbxdata['objects'][obj['mainGroup']]
        return obj['mainGroup'], maingroup
    
    def getGroup(self, group_path, createGroup = True):
        found = self._get_group(group_path)
        if found:
            return createPbxObject(found[0])
        elif createGroup :
            key, _ = self.add_group(group_path)
            return createPbxObject(key)
        else:
            return None
        
    
    def add_group(self,group_path, children=()):
        ''' project에 group을 생성한다.
        
        |group_path|에서 주어진 경로를 찾아보고 없으면 group를 만든다.
        '''
        
        # 기존에 있으면 해달 group를 return 
        group = self._get_group(group_path)
        if group : return group
        
        # 없으면 가장 맞는 group를 찾아보고 없으면 만든다.
        path = group_path.rstrip('/')
        
        # /a/b/c 경로에서 먼저 뒤 경로를 제거하고 찾아본다.
        # 경로상에서 존제하는 group를 찾는다.
        exist_group = self._get_group('/')
        nonexists_group = []
        while path:
            group = self._get_group(path)
            if group :
                exist_group = group
                break
            else:
                nonexists_group.insert(0,path.split('/')[-1])
                path = '/'.join(path.split('/')[:-1])
        
        # 결로상에 없는 group를 만든다.
        curgroup = exist_group
        for g in nonexists_group:
            # group 생
            groupguid = self._create_guid()
            groupobj = {"isa":"PBXGroup",
                        "name":g,
                        "sourceTree":"<group>",
                        "children":()}
            
            self.pbxdata['objects'][groupguid] = groupobj
            # curgroup의 children에 추
            curgroup[1]['children']+=(groupguid,)
            
            # curgroup 변경 
            curgroup = (groupguid, groupobj)
         
        return curgroup
    
        
    
    def _get_group(self, group_path):
        ''' path형태로 표현한 group를 찾아 준다.
        
        / 로 시작하면 root 부터 찾는 절대경로의 group를 찾
        아닌경우에는 맞는 이름으로 검색한다.
        '''
        path = group_path.strip('/').split('/')
        groups = dict(self.objects_if({'isa':'PBXGroup'}))
        is_abs_path = group_path.startswith('/')
        
        curgroup = None
        curgroupkey = None
        
        if is_abs_path:
            curgroupkey, curgroup = self._get_root_group()

        else:
            for k,v in groups.iteritems():
                if (v.get('name') == path[0] or v.get('path') == path[0]):
                    curgroupkey,curgroup = k,v
                    path.pop(0)
                    break
        
        found = True        
        for p in path:
            if not p: continue
            found = False
            for guid in curgroup['children']:
                group = groups.get(guid)
                if group and ( group.get('name') == p or group.get('path') == p):
                    curgroup = group
                    curgroupkey = guid
                    found = True
                    break
            
        if found:
            return curgroupkey,curgroup
        return None
    
        
    def _add_item_to_group(self, guid, group_path):
        group = self._get_group(group_path)
        group['children'] += guid
        return guid
        

    
    def _add_file_to_frameworks_phase(self, libfile_hash):
        guid, framework_phase = self.object_if({'isa':'PBXFrameworksBuildPhase'})
        if not framework_phase : return False
        framework_phase['files'] += (libfile_hash,)
        return True
    
    def _get_bundletype(self, filename):
        get_bundletype(filename)
    

    
    def _add_file_to_bundle_phase(self, file_hash):
        guid, phase = self.object({'isa':'PBXResourcesBuildPhase'})
        if not phase : return False
        phase['files'] += (file_hash,)
        return True

    
    def _add_file_to_group(self, fileref_hash,group_path):
        guid, group = self.add_group(group_path) 
        if not group : return False
        
        group['children'] += (fileref_hash,)
        return True
    
    def _add_file_to_source_phase(self, file_hash):
        guid, phase = self.object_if({'isa':'PBXSourcesBuildPhase'})
        if not phase : return False
        phase['files'] += (file_hash,)
        return True
    
    
    def _add_project_proxy(self, fileref, project_path):
        ''' project container proxy 생성
            
            return : ( (<guid>,<obj>,<productfilename>)...)
        '''
        
        pbx = PbxProject.loadPbxproj(project_path)
        if not pbx: return None
        
        ret = []
        targets = pbx.objects_if({'isa':'PBXNativeTarget'})
        for _,target in targets:
            
            # check exists object
            obj = self.object_if({'isa':'PBXContainerItemProxy', 'containerPortal':fileref, 'proxyType':2, 'remoteGlobalIDString':target['productReference']})
            if not obj :
                obj = {'isa' : 'PBXContainerItemProxy',
                       'containerPortal' : fileref,
                       'proxyType' : 2,                 # just add project
                       'remoteGlobalIDString' : target['productReference'],
                       'remoteInfo' : target['productName'] }
                guid = self._create_guid()
                self.pbxdata['objects'][guid] = obj
            else:
                guid,obj = obj

                
            ret.append((guid,obj,pbx.object(target['productReference'])['path']))
            
        return ret
    
    def _add_referenceproxy(self,filename, proxyguid):
        'referenceproxy 추가'
        obj = self.object_if({'isa':'PBXReferenceProxy','remoteRef':proxyguid})
        if not obj:
            obj = {'isa' : 'PBXReferenceProxy',
                   'fileType' : get_bundletype(filename),
                   'path' : filename,           
                   'remoteRef' : proxyguid,
                   'sourceTree' : 'BUILT_PRODUCTS_DIR' }
    
            guid = self._create_guid()
        else:
            guid,obj = obj

        self.pbxdata['objects'][guid] = obj
        
        return guid
    
    def _get_filepath_from_fileref_or_buildfileguid(self, filerefguid):
        allobjs = self.pbxdata['objects']
        filerefobj = allobjs.get(filerefguid)
        if not filerefobj : return None
            
        if filerefobj['isa']!='PBXFileReference': 
            filerefobj = allobjs.get(filerefobj['fileRef'])
        
        return filerefobj['path']
    
    
    def hasGuid(self,guid):
        return self.pbxdata['objects'].get(guid) != None

    def createPbxGuid(self):
        'guid 생성'
        import time
        import random
        while True :
            uniquehash = hashlib.sha224(str(random.random())).hexdigest().upper()
            uniquehash = uniquehash[:24]
            if not self._exist_guid(uniquehash) : break;    
            
        return uniquehash
    
    _create_guid = createPbxGuid
    _exist_guid = hasGuid
    
    def getPbxTargets(self):
        return self.getAllObjects(isa='PBXNativeTarget')
    
    def setObject(self,key,val):
        self.pbxdata['objects'][key] = val
        
    def removeObject(self, guid):
        if guid in self.pbxdata['objects'].keys():
            del self.pbxdata['objects'][guid]
        
    def getAllGroups(self):
        return self.getAllObjects(isa='PBXGroup')
    
    def getAllObjects(self, **conds):
        objs = self.pbxdata['objects']
        ret = []
        if not objs: return ret
        
        for guid, obj in objs.iteritems():
            
            # check condition
            for ck,cv in conds.iteritems():
                v = obj.get(ck)
                if not v : break;
                if isinstance(v, (list, tuple)) and cv not in v : break;
                if not isinstance(v, (list, tuple)) and cv != v : break;

            else:
                # all codition ok
                obj = createPbxObject(self.pbxproj, guid)
                ret.append(obj)

        return ret
    
    def getAllObjectsWithConditions(self, cond):
        '주어진 |cond|를 가진 object구하기, |cond|는 dict type 이여야 한다.'
        if not isinstance(cond,dict): return []
        
        objs = self.pbxproj.objects_if(cond)
        ret = []
        if not objs: return ret
        for guid, _ in objs:
            obj = createPbxObject(self.pbxproj, guid)
            ret.append(obj)

        return ret
    
    def getAllObjectsHasGuid(self, guid):
        '주어진 |guid|를 가지고 있는 object 구하기'
        objs = self.pbxdata['objects']
        ret = []
        if not objs: return ret
        
        for k, v in objs.iteritems():
            for _, subv in v.iteritems():
                if isinstance(subv,(list,tuple)):
                    if guid in subv:
                        ret.append(createPbxObject(self.pbxproj, k))
                        break
                    # projectReferences of PBXProject
                    if _ == 'projectReferences' and subv and guid in reduce(operator.add,[ x.values() for x in subv]) :
                        ret.append(createPbxObject(self.pbxproj, k))
                        break
                    
                elif isinstance(subv,(str,unicode)):
                    if guid == subv:
                        ret.append(createPbxObject(self.pbxproj, k))
                        break
                elif isinstance(subv,dict):
                    for sskey,ssval in subv.iteritems():
                        if guid == ssval or guid == sskey:
                            ret.append(createPbxObject(self.pbxproj, k))
                            
        return ret
        
    def getDefaultTarget(self):
        try:
            target = self.getPbxTargets()[0]
        except:
            target = None
            
        return target
    
    def getConfigureList(self):
        guid = self.get('buildConfigurationList')
        if not guid : return None
        return createPbxObject(self.pbxproj, guid)
    
def createPbxObject(pbxproj, guid):
    obj = pbxproj.pbxdata['objects'].get(guid)
    if not obj : return None
    
    isa = obj['isa']
    
    def getClassForType(name):
        class_name = ''
        if name[:3] == 'PBX':
            class_name = 'Pbx' + name[3:]
        elif name[:2] == 'XC':
            class_name = 'Pbx' + name[2:]
            
        cls = globals().get(class_name)
        if not cls : cls = PbxObject
        
        return cls
    
    return getClassForType(isa)(pbxproj, guid)

class PbxBuildConfigurationList(PbxObject):
    def __init__(self, pbxproj, guid):
        PbxObject.__init__(self, pbxproj, guid)
        
    def visible(self):
        return bool( self.get('defaultConfigurationIsVisible') )
    
    def defaultConfiguration(self):
        return self.get('defaultConfigurationName')
    
    def getConfigurations(self):
        guids = self.get('buildConfigurations')
        if not guids : return []
        
        ret = []
        for g in guids:
            ret.append(createPbxObject(g))

        return ret
    
    def addConfiguration(self, configuration):
        if isinstance(configuration, PbxBuildConfiguration):
            self.appendValue('buildConfigurations', configuration.getGuid())
        elif isinstance(configuration, (str,unicode)):
            self.appendValue('buildConfigurations', configuration)
        
    def removeConfiguration(self, configuration):
        if isinstance(configuration, PbxBuildConfiguration):
            self.removeValue('buildConfigurations', configuration.getGuid())
        elif isinstance(configuration, (str,unicode)):
            self.removeValue('buildConfigurations', configuration)
        

class PbxBuildConfiguration(PbxObject):
    def __init__(self, pbxproj, guid):
        PbxObject.__init__(self, pbxproj, guid)
    
    @staticmethod
    def createObject(pbxproj,name,settings):
        obj = { 'isa' : 'XCBuildConfiguration',
                'name' : name,
                'buildSettings' : settings }
        guid = pbxproj.createPbxGuid()
        pbxproj.setObject(guid, obj)
        return createPbxObject(pbxproj,guid)
    
    def setSettings(self, key, value):
        settings = self.get('buildSettings')
        settings[key] = value
        
    def getSetting(self, key):
        settings = self.get('buildSettings')
        return settings[key]
    
    def __str__(self):
        return str(self.obj)
    
    
class PbxBuildFile(PbxObject):
    def __init__(self, pbxproj, guid):
        PbxObject.__init__(self, pbxproj, guid)
        try:
            self.fileref = PbxFileReference(pbxproj, self.get('fileRef'))
        except:
            self.fileref = None
        
    def getPath(self):
        if not self.fileref : return ""
        return self.fileref.get('path')
    
    def getAbspath(self):
        if not self.fileref : return ""
        return self.fileref.getAbspath()
    
    def getSourceTree(self):
        if not self.fileref : return ""
        return self.fileref.get('sourceType')
    
    @staticmethod
    def createObject(pbxproj, fileref):
        if isinstance(fileref, PbxObject):
            fileref = fileref.getGuid()
        
        obj = { 'isa' : 'PBXBuildFile',
                'fileRef' : fileref }
        guid = pbxproj.createPbxGuid()
        pbxproj.setObject(guid, obj)
        
        return createPbxObject(pbxproj, guid)

    @staticmethod
    def createObjectFromPath(pbxproj, path):
        
        fileref = PbxFileReference.createObject(pbxproj, path)
        
        return PbxBuildFile.createObject(pbxproj, fileref)
        
    
    def __str__(self):
        return '(PBXBuildFile : %s)' % self.fileref
        
class PbxBuildPhase(PbxObject):
    def __init__(self, pbxproj, guid):
        PbxObject.__init__(self, pbxproj, guid)
        
    def getPhaseName(self):
        isa = self.get('isa')
        return isa
    
    def getBuildActionMask(self):
        return self.get('buildActionMask')
    
    def isPostProcessing(self):
        return bool(self.get('runOnlyForDeploymentPostprocessing'))
    
    def getFiles(self):
        guids = self.get('files')
        ret = []
        for guid in guids:
            ret.append(createPbxObject(self.pbxproj, guid))
            
        return ret
    
    def addFile(self, fileguid):
        return self.appendValue('files', fileguid)
    
    def removeFile(self, fileguid):
        return self.removeValue('files', fileguid)

class PbxFrameworksBuildPhase(PbxBuildPhase):
    def __init__(self, pbxproj, guid):
        PbxBuildPhase.__init__(self, pbxproj, guid)


class PbxHeadersBuildPhase(PbxBuildPhase):
    def __init__(self, pbxproj, guid):
        PbxBuildPhase.__init__(self, pbxproj, guid)

class PbxSourcesBuildPhase(PbxBuildPhase):
    def __init__(self, pbxproj, guid):
        PbxBuildPhase.__init__(self, pbxproj, guid)

class PbxResourcesBuildPhase(PbxBuildPhase):
    def __init__(self, pbxproj, guid):
        PbxBuildPhase.__init__(self, pbxproj, guid)

    
class PbxFileReference(PbxObject):
    def __init__(self, pbxproj, guid):
        PbxObject.__init__(self, pbxproj, guid)
        
    def getPath(self):
        return self.get('path')
    
    def getAbspath(self):
        relpath = self.getPath()
        groups = self.pbxproj.getAllObjects(isa='PBXGroup', children=self.getGuid())
        path = [self.pbxproj.getRootPath()]
        if groups: path = [groups[0].getAbspath()]
        path.append(relpath)
        ret = os.path.abspath(reduce(os.path.join,path))
        return ret
    
    def getGroup(self):
        groups = self.pbxproj.getAllObjects(isa='PBXGroup', children=self.getGuid())
        if groups: return groups[0]
        return None
        
    
    def getSourceTree(self):
        return self.get('sourceType')

    @staticmethod
    def createObject(pbxproj, path):
        rel_path = path
        src_tree = '<group>'
        file_type = get_bundletype(path)

        if file_type == 'wrapper.pb-projec':
            rel_path = pbxproj.getRelPathFromProjPath(path)
        elif file_type == 'wrapper.framework':
            src_tree = 'SDKROOT'
        
        obj = { 'isa': 'PBXFileReference',
                'lastKnownFileType': file_type,
                'name':os.path.basename(path),
                'path':rel_path,
                'sourceTree':src_tree}
        
        guid = pbxproj.createPbxGuid()
        
        pbxproj.setObject(guid, obj)
        return createPbxObject(pbxproj,guid)
    
    def __str__(self):
        return '< path = %s, sourceTree = %s > ' % (self.getPath(), self.getSourceTree())
    

class PbxContainerItemProxy(PbxObject):
    def __init__(self, pbxproj, guid):
        PbxObject.__init__(self,pbxproj, guid)

class PbxVersionGroup(PbxObject):
    def __init__(self, pbxproj, guid):
        PbxObject.__init__(self,pbxproj, guid)
        
class PbxVariantGroup(PbxObject):
    def __init__(self, pbxproj, guid):
        PbxObject.__init__(self,pbxproj, guid)
        
class PbxReferenceProxy(PbxObject):
    def __init__(self, pbxproj, guid):
        PbxObject.__init__(self,pbxproj, guid)

class PbxTargetDependency(PbxObject):
    def __init__(self, pbxproj, guid):
        PbxObject.__init__(self,pbxproj, guid)

class PbxGroup(PbxObject):
    def __init__(self, pbxproj, guid):
        PbxObject.__init__(self,pbxproj, guid)

    def getParentGroup(self):
        for group in self.pbxproj.getAllGroups():
            for g in group.getSubgroups():
                if g.guid == self.guid:
                    return group
        return None 
        
    def getSubgroups(self):
        ret = []
        for guid in self.get('children'):
            obj = createPbxObject(self.pbxproj, guid)
            if isinstance(obj, PbxGroup):
                ret.append(obj)
        return ret
    
    def getSubfiles(self):
        '하위 files'
        ret = []
        for guid in self.get('children'):
            obj = createPbxObject(self.pbxproj, guid)
            if not isinstance(obj, PbxGroup):
                ret.append(obj)            
        return ret
    
    def getName(self):
        ret = self.get('name')
        return ret
    
    def getPath(self):
        ret = self.get('path')
        return ret
    
    def getAbspath(self):
        curgroup = self
        path = []
        while curgroup:
            p = curgroup.get('path')
            if p:
                path.insert(0,p)
            curgroup = curgroup.getParentGroup()
        
        path.insert(0, self.pbxproj.getRootPath())
        
        return os.path.abspath(os.path.normcase(reduce(os.path.join,path)))
    
    def addFileReference(self, fileref):
        assert isinstance(fileref, PbxFileReference)
        
        if os.path.isabs(fileref.getPath()):
            fileref.set('path', os.path.relpath(fileref.getPath(), self.getAbspath()))
            
        self.appendValue('children', fileref.getGuid())
        
    def addGroup(self, group):
        self.appendValue('children', group.getGuid())
    
    def getGroupFromPath(self, group_path):
        path = group_path.strip('/').split('/')

        found = True     
        curgroup = self   
        for p in path:
            if not p: continue
            found = False
            for subgroup in curgroup.getSubgroups():
                if subgroup.getName() == p or subgroup.getPath() == p:
                    curgroup = subgroup
                    found = True
                    break
            
        if found:
            return curgroup
        return None
    
    @staticmethod
    def createObject(pbxproj, name):
        guid = pbxproj.createPbxGuid()
        obj = {"isa":"PBXGroup",
                    "name":name,
                    "sourceTree":"<group>",
                    "children":()}
        pbxproj.setObject(guid, obj)
        return createPbxObject(pbxproj,guid)
    
    def addGroupFromPath(self, group_path):
        path = group_path.strip('/').split('/')
        curgroup = self   
        for p in path:
            if not p: continue
            found = False
            for subgroup in curgroup.getSubgroups():
                if subgroup.getName() == p or subgroup.getPath() == p:
                    curgroup = subgroup
                    found = True
                    break
            if not found:
                newGroup = PbxGroup.createObject(self.pbxproj, p)
                curgroup.addGroup(newGroup)
                curgroup = newGroup
                
        return curgroup
    
    
    def __str__(self):
        return '(%d : type: PBXGroup, name:%s, path %s) ' % (id(self), self.getName(), self.getPath())
    
    
class PbxNativeTarget(PbxObject):
    ''' PBXNativeTarget 정보 조회 및 수정을 위한 Class.
    '''
    def __init__(self, pbxproj, guid):
        PbxObject.__init__(self,pbxproj, guid)
        
    def getConfigurations(self):
        configlistguid = self.get('buildConfigurationList')
        return createPbxObject(self.pbxproj, configlistguid)
    
    def getBuildPhases(self):
        guids = self.get('buildPhases')
        ret = []
        for guid in guids:
            ret.append(createPbxObject(self.pbxproj, guid))
            
        return ret
        
    def getBuildSourcesPhasesFromType(self, typename):
        phases = self.getBuildPhases()
        for p in phases:
            if p.getPhaseName() == typename:
                return p
        return None

    def getBuildHeadersPhase(self):
        return self.getBuildSourcesPhasesFromType('PBXHeadersBuildPhase')
    
    def getBuildSourcesPhase(self):
        return self.getBuildSourcesPhasesFromType('PBXSourcesBuildPhase')
    
    def getBuildFrameworksPhase(self):
        return self.getBuildSourcesPhasesFromType('PBXFrameworksBuildPhase')

    def getBuildResourcesPhase(self):
        return self.getBuildSourcesPhasesFromType('PBXResourcesBuildPhase')
    
    def getDependencies(self):
        return None
    
    def getName(self):
        return self.get('name')
    
    def getProductName(self):
        return self.get('productName')
    
    def getProductFileName(self):
        guid = self.get('productReference')
        if not guid: return ''
        
        fileref = createPbxObject(self.pbxproj, guid)
        return fileref.getPath()
    
    def getProductReference(self):
        return PbxFileReference(self.pbxproj, self.get('productReference'))
    
    def getProductType(self):
        return self.get('productType')
    
    def addFramework(self, framework):
        fileref_hash = self.pbxproj._add_filereference(framework, 'wrapper.framework', self.pbxproj.createPbxGuid(), 'System/Library/Frameworks/'+framework, 'SDKROOT')
        libfile_hash = self.pbxproj._add_buildfile(fileref_hash, self.pbxproj.createPbxGuid())
        
        if not self.pbxproj._add_file_to_group(fileref_hash,"Frameworks"):
            return False

        self.getBuildFrameworksPhase().addFile(libfile_hash)
        
        return True
    
    def removeFramework(self, framework):
        obj = self.pbxproj.object_if({'isa':'PBXFileReference', 'lastKnownFileType':'wrapper.framework', 'path':framework})
        if not obj :
            obj = self.pbxproj.object_if({'isa':'PBXFileReference', 'lastKnownFileType':'wrapper.framework', 'name':framework})
            
        if not obj : return False
        
        # file ref 제거
        fileref = obj[0]
        self.pbxproj.removeObject(fileref)
        
        # build file ref 제거
        buildref = None
        obj = self.pbxproj.object_if({'isa':'PBXBuildFile', 'fileRef':fileref})
        if obj :
            buildref = obj[0]
            self.pbxproj.removeObject(buildref)

        # build framework phase 에서 제거 ( build file ref 이용 )
        self.getBuildFrameworksPhase().removeFile(buildref)

        # group 제거 ( file ref 이용 )
        groups = self.pbxproj.getAllGroups()
        for g in groups:
            if fileref in g.get('children'):
                g.removeValue('children', fileref)
        
        return True
    
    def getFrameworks(self):
        ret = []
        for f in self.getBuildFrameworksPhase().getFiles():
            if f.getPath().endswith('.framework'):
                ret.append(f.getPath())
        
        return ret
    
    def addTargetDependency(self, dep_targetname):
        # target container proxy 찾기 
        try:
            guid, obj = self.pbxproj.object_if({'isa':'PBXReferenceProxy','path':dep_targetname})
            container_proxy = self.pbxproj.object(obj['remoteRef'])
        except:
            return False
        
        # container item proxy 생성
        try:
            proj_file_ref = container_proxy['containerPortal']
        except:
            print container_proxy
            
        proj_file_obj = self.pbxproj.object(proj_file_ref)
        project_path = self.pbxproj.getAbsPathFromRelProjPath(proj_file_obj['path'])
        pbx = PbxProject.loadPbxproj(project_path)
        if not pbx: return False
        
        dep_target = pbx.object_if({'productReference':container_proxy['remoteGlobalIDString']})
        if not dep_target:return False
        
        # 기존에 container가 있는지 확인 
        targetproxy = None
        try:
            container = self.pbxproj.object_if({'remoteGlobalIDString':dep_target[0]})
            if container: targetproxy = container[0]
        except:
            return False
        
        if not targetproxy:
            obj = copy.deepcopy(container_proxy)
            obj['proxyType'] = '1'
            obj['remoteGlobalIDString'] = dep_target[0]
            guid = self.pbxproj.createPbxGuid()
            self.pbxproj.setObject(guid, obj)
            targetproxy = guid
        
        # target dependency 생성
        obj = {'isa' : 'PBXTargetDependency',
               'name' : dep_target[1]['name'],
               'targetProxy' : targetproxy }
        
        guid = self.pbxproj.createPbxGuid()
        self.pbxproj.setObject(guid, obj)
        
        targetdependencyguid = guid
         
        # target oejct에 dependcy 설정
        self.appendValue('dependencies', targetdependencyguid)
         
        return True
    
    def removeTargetDependency(self, dep_targetname):
        # 기존에 container가 있는지 확인
        try:
            containers = self.pbxproj.objects_if({'isa':'PBXContainerItemProxy','proxyType':"1"})
            found = False
            for container_key, container_obj in containers:
                proj_file_ref = container_obj['containerPortal']
                proj_file_obj = self.pbxproj.object(proj_file_ref)
                project_path = self.pbxproj.getAbsPathFromRelProjPath(proj_file_obj['path'])
                pbx = PbxProject.loadPbxproj(project_path)
            
                if not pbx: continue
                
                dep_target = pbx.object(container_obj['remoteGlobalIDString'])
                if not dep_target: continue
                
                filerefobj = pbx.object(dep_target['productReference'])
                if not filerefobj : continue
                
                if filerefobj['path'] == dep_targetname:
                    found = True
                    break
            
            if not found : return False
            
            # container 제거     
            self.pbxproj.removeObject(container_key)
            
            # target dependency 제거 
            target_dependency = self.pbxproj.object_if({'isa':'PBXTargetDependency', 'targetProxy':container_key})
            if not target_dependency : return False
            self.pbxproj.removeObject(target_dependency[0])
            
            # dependency 제거
            self.removeValue('dependencies', target_dependency[0])
            
        except:
            return False
        
        return True
    
    def addSource(self, path, group = None):
        assert os.path.exists(path)
        if not group :
            group = self.pbxproj.getMainGroup()

        # get file reference ( local file )
        filerefs = self.pbxproj.getAllObjects(isa='PBXFileReference', path=path)
        if not filerefs:
            filerefs = self.pbxproj.getAllObjects(isa='PBXFileReference')
            filerefs = filter(lambda x : x.getAbspath() == path, filerefs)
            
            # if exists already.
            if filerefs: return False
            
            # not have file reference
            obj = PbxFileReference.createObject(self.pbxproj, path)
            group.addFileReference(obj)
            fileref_hash = obj.getGuid()
        
        # add build file
        buildfile = PbxGroup.createObject(self.pbxproj, fileref_hash)
        
        # add PBXFrameworksBuildPhase
        self.getBuildSourcesPhase().appendValue('files',buildfile.getGuid())

        return True
    
    def addHeader(self, path, group = None):
        assert os.path.exists(path)
        if not group :
            group = self.pbxproj.getMainGroup()

        # get file reference ( local file )
        filerefs = self.pbxproj.getAllObjects(isa='PBXFileReference', path=path)
        if not filerefs:
            filerefs = self.pbxproj.getAllObjects(isa='PBXFileReference')
            filerefs = filter(lambda x : x.getAbspath() == path, filerefs)
            
            # if exists already.
            if filerefs: return False
            
            # not have file reference
            obj = PbxFileReference.createObject(self.pbxproj, path)
            group.addFileReference(obj)
            fileref_hash = obj.getGuid()
        
        # add build file
        buildfile = PbxGroup.createObject(self.pbxproj, fileref_hash)
        
        # add PBXFrameworksBuildPhase
        self.getBuildHeadersPhase().appendValue('files',buildfile.getGuid())
        return True
    
    def addResource(self, path, group = None):
        assert os.path.exists(path)
        if not group :
            group = self.pbxproj.getMainGroup()

        # get file reference ( local file )
        filerefs = self.pbxproj.getAllObjects(isa='PBXFileReference', path=path)
        if not filerefs:
            filerefs = self.pbxproj.getAllObjects(isa='PBXFileReference')
            filerefs = filter(lambda x : x.getAbspath() == path, filerefs)
            
            # if exists already.
            if filerefs: return False
            
            # not have file reference
            obj = PbxFileReference.createObject(self.pbxproj, path)
            group.addFileReference(obj)
            fileref_hash = obj.getGuid()
        
        # add build file
        buildfile = PbxGroup.createObject(self.pbxproj, fileref_hash)
        
        # add PBXFrameworksBuildPhase
        self.getBuildResourcesPhase().appendValue('files',buildfile.getGuid())
        return True
    
    def addLibrary(self, libname, group = None):
        # libname must be library path or library name of other project
        assert os.path.exists(libname) or os.path.basename(libname) == libname
        
        if not group :
            group = self.pbxproj.getMainGroup()

        # get file reference ( other project file )
        filerefs = self.pbxproj.getAllObjects(isa='PBXReferenceProxy', path=libname)
        if filerefs:
            fileref_hash = filerefs[0].getGuid()
        
        # get file reference ( local file )
        if not filerefs:
            filerefs = self.pbxproj.getAllObjects(isa='PBXFileReference', path=libname)
            if not filerefs:
                filerefs = self.pbxproj.getAllObjects(isa='PBXFileReference')
                filerefs = filter(lambda x : x.getAbspath() == libname, filerefs)
                
                # if exists already.
                if filerefs: return False
                
                # not have file reference
                obj = PbxFileReference.createObject(self.pbxproj, libname)
                group.addFileReference(obj)
                fileref_hash = obj.getGuid()
        
        # add build file
        buildfile = self.pbxproj.getAllObjects(isa='PBXBuildFile',fileRef=fileref_hash)
        if not buildfile:
            libfile_hash = self.pbxproj._add_buildfile(fileref_hash, self.pbxproj.createPbxGuid())
        else:
            libfile_hash = buildfile[0].getGuid()
        
        # add PBXFrameworksBuildPhase
        self.getBuildFrameworksPhase().appendValue('files',libfile_hash)

        return True
    
    def removeLibrary(self, libname):
        # remove file reference
        filerefs = self.pbxproj.getAllObjects(isa='PBXFileReference', path=libname)
        if not filerefs:
            filerefs = self.pbxproj.getAllObjects(isa='PBXFileReference')
            filerefs = filter(lambda x : x.getAbspath() == libname, filerefs)

        # if exists already.
        if not filerefs: return False
        
        fileref = filerefs[0]
        fileref.removeObjectFromRoot()
        
        # remove build file ref
        buildfiles = self.pbxproj.getAllObjects(isa='PBXBuildFile',fileRef = fileref.getGuid())
        if not buildfiles: return False
        
        buildfile = buildfiles[0]
        buildfile.removeObjectFromRoot()
        
        # remove file in groups
        group = fileref.getGroup()
        if group:
            group.removeValue('children', fileref.getGuid())
        
        #  remove PBXFrameworksBuildPhase
        self.getBuildFrameworksPhase().removeValue('files',buildfile.getGuid())

        return True

    def getBuildHeaders(self):
        phase = self.getBuildHeadersPhase()
        if not phase: return []
        
        # file guid
        files = phase.getFiles()
                
        return files        
    
     
    def getBuildSources(self):
        phase = self.getBuildSourcesPhase()
        if not phase: return []
        
        # file guid
        files = phase.getFiles()
        return files
    
    def isLibrary(self):
        return self.get('productType') == "com.apple.product-type.library.static"
    
    
    
class PbxprojTestCase(unittest.TestCase):
    def setUp(self):
        self.source = '~/Desktop/aa/aa.xcodeproj'
        self.pbx = PbxProject.loadPbxproj(self.source)

    def testListFramework(self):
        try:
            target = self.pbx.getPbxTargets()[0]
            frameworks = target.getFrameworks()
            print frameworks
        except:
            pass

    def nottestNativeTarget(self):
        targets = self.pbx.getPbxTargets()
        self.assertTrue(targets, 'cannot find native target')
        
        target = targets[0]
        configs = target.getConfigurations()
        
        print configs.visible()
        print configs.defaultConfiguration()
        
        print target.getBuildResourcesPhase()
        
        PbxFileReference.createObject(self.pbx, self.source)
        PbxBuildFile.createObjectFromPath(self.pbx, 'asdf.m')
        #self.pbx.saveas('/Users/jinni/temp/test.pbxproj')
        
        
    def nottestGroup(self):
        maingroup = self.pbx.getMainGroup()
        
        for i in maingroup.getSubgroups():
            print i
            
        gg = maingroup.addGroupFromPath('sdsd/a/12/4')
        ff = maingroup.getGroupFromPath('sdsd/a/12/4')
        self.assertEqual(gg.guid, ff.guid, "cannot add group")
        

    def testAddFramework(self):
        try:
            target = self.pbx.getPbxTargets()[0]
        except:
            target = None
        
        target.addFramework('QuartzCore.framework')
        target.addFramework('AddressBook.framework')
        target.addFramework('AddressBookUI.framework')
        
        framworks = target.getFrameworks()
        self.assertIn('System/Library/Frameworks/QuartzCore.framework', framworks, "QuartzCore not in frameworks")
        self.assertIn('System/Library/Frameworks/AddressBook.framework', framworks, "AddressBook not in frameworks")
        self.assertIn('System/Library/Frameworks/AddressBookUI.framework', framworks, "AddressBookUI not in frameworks")
        
        target.removeFramework('AddressBookUI.framework')

        framworks = target.getFrameworks()
        self.assertIn('System/Library/Frameworks/QuartzCore.framework', framworks, "QuartzCore not in frameworks")
        self.assertIn('System/Library/Frameworks/AddressBook.framework', framworks, "AddressBook not in frameworks")
        self.assertNotIn('System/Library/Frameworks/AddressBookUI.framework', framworks, "AddressBookUI not in frameworks")
        self.pbx.save()
        #print self.pbx
        
    
    def nottestAddProject(self):
        self.pbx.addProject('/Users/jinni/bb/bb.xcodeproj')
        target = self.pbx.getDefaultTarget()
        target.addTargetDependency('libPushPlugin.a')
        target.addTargetDependency('libPushSendTestPlugin.a')
        target.addLibrary('libPushPlugin.a')
        target.addLibrary('libPushSendTestPlugin.a')
        target.removeLibrary('libPushPlugin.a')
        target.removeLibrary('libPushSendTestPlugin.a')
        target.removeTargetDependency('libPushSendTestPlugin.a')
        
        #print self.pbx
        self.pbx.save()
        
    def nottestCreatePbxProj(self):
        pbx = PbxProject.createPbxproj(os.path.expanduser('~/temp/test.xcproj'))
        config = PbxBuildConfiguration.createObject(pbx, 'Debug', {'ALWAYS_SEARCH_USER_PATHS' : True})
        pbx.getConfigureList().addConfiguration(config)
        
        print pbx.getConfigureList()
        print pbx
        pbx.save()
        
                
if __name__=='__main__':
    unittest.main()
    
