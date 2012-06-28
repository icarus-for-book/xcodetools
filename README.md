iOS Tools
===========

iOS 앱을 개발하면서 필요한 파이션 모듈 및 유틸리티들


convertImages.py
---------------

주어진 이미지를 iOS앱이 필요한 사이즈의 파일들로 만들 수 
있는 유틸

## 위치

> bin/convertImages.py


### 사용 방법


> $> chmod +x convertImages.py

convertImages.py에 실행 모드를 추가한다. 

> $> convertImages.py -o outdir BIG_IMAGE.png

512x512 이상되는 아이콘 이미지를 넣으면 outdir에 
iOS앱이 필요한 이미지들이 만들어 진다. 


pbxlib.py
---------

Xcode의 프로젝트를 파일을 분석하거나 수정할 수 있는 
python 라이브러리

### 파일 위치

> xcodetools/pbxlib.py

xcodelib.py
-------------

xcodebuild 를 통해서 Xcode 프로젝트를 빌드할 수 있는 
python 라이브러리 

### 파일 위치

> xcodetools/xcodelib.py

