#!/usr/bin/env python3
"""Generate a dependency-free Xcode project; no XcodeGen/CocoaPods needed."""
from pathlib import Path
import hashlib
import plistlib
import json
import re
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
objects = {}
def uid(name): return hashlib.sha256(name.encode()).hexdigest()[:24].upper()
def obj(identity, isa, **fields):
    identifier = uid(identity)
    objects[identifier] = dict(isa=isa, **fields)
    return identifier
def q(s): return json.dumps(str(s), ensure_ascii=False)
def render(value, depth=0):
    indent = '\t' * depth
    if isinstance(value, dict):
        return '{\n' + ''.join(f'{indent}\t{q(k)} = {render(v, depth + 1)};\n' for k, v in value.items()) + indent + '}'
    if isinstance(value, list):
        return '(\n' + ''.join(f'{indent}\t{render(v, depth + 1)},\n' for v in value) + indent + ')' if value else '()'
    return q(value)
def file(name, path, kind, source_tree='SOURCE_ROOT'):
    return obj(name, 'PBXFileReference', lastKnownFileType=kind, path=path, sourceTree=source_tree)
def build(name, reference, **kwargs): return obj(name, 'PBXBuildFile', fileRef=reference, **kwargs)

def main():
    objects.clear()
    terms = (ROOT / 'docs/USER_TERMS_DRAFT_ZH.md').read_text(encoding='utf-8')
    (ROOT / 'App/TERMS_DRAFT.txt').write_text(re.sub(r'^#+ ', '', terms, flags=re.M), encoding='utf-8')
    app_sources = ['App/ZhuyinBridgeApp.swift']
    keyboard_sources = ['KeyboardExtension/KeyboardViewController.swift', 'Shared/BridgeEngine.swift', 'Shared/BridgeData.swift']
    refs = {p: file(p, p, 'sourcecode.swift') for p in app_sources+keyboard_sources}
    terms = file('terms', 'App/TERMS_DRAFT.txt', 'text')
    privacy = file('privacy', 'PrivacyInfo.xcprivacy', 'text.xml')
    refs['App/Info.plist'] = file('appplist','App/Info.plist','text.plist.xml')
    refs['KeyboardExtension/Info.plist'] = file('extplist','KeyboardExtension/Info.plist','text.plist.xml')
    app_product = file('appProduct','ZhuyinBridge.app','wrapper.application','BUILT_PRODUCTS_DIR')
    ext_product = file('extProduct','ZhuyinBridgeKeyboard.appex','wrapper.app-extension','BUILT_PRODUCTS_DIR')
    products = obj('products','PBXGroup', children=[app_product,ext_product], name='Products', sourceTree='<group>')
    group = obj('rootGroup','PBXGroup', children=list(refs.values())+[terms,privacy,products], sourceTree='<group>')
    def sources(name,paths):
        return obj(name,'PBXSourcesBuildPhase', buildActionMask='2147483647', files=[build(name+p,refs[p]) for p in paths],runOnlyForDeploymentPostprocessing='0')
    def resources(name,items):
        return obj(name,'PBXResourcesBuildPhase', buildActionMask='2147483647', files=[build(name+r,r) for r in items],runOnlyForDeploymentPostprocessing='0')
    def frameworks(name):return obj(name,'PBXFrameworksBuildPhase',buildActionMask='2147483647',files=[],runOnlyForDeploymentPostprocessing='0')
    common={'CLANG_ENABLE_MODULES':'YES','IPHONEOS_DEPLOYMENT_TARGET':'16.0','SDKROOT':'iphoneos','SWIFT_VERSION':'5.0','TARGETED_DEVICE_FAMILY':'1,2','CODE_SIGN_STYLE':'Automatic','DEVELOPMENT_TEAM':'','MARKETING_VERSION':'0.1.0','CURRENT_PROJECT_VERSION':'1'}
    def configs(name,extra):
        ids=[]
        for config in ('Debug','Release'):
            settings={**common,**extra,'SWIFT_OPTIMIZATION_LEVEL':'-Onone' if config=='Debug' else '-O','DEBUG_INFORMATION_FORMAT':'dwarf' if config=='Debug' else 'dwarf-with-dsym'}
            if config=='Debug': settings['SWIFT_ACTIVE_COMPILATION_CONDITIONS']='DEBUG'
            ids.append(obj(name+config,'XCBuildConfiguration',name=config,buildSettings=settings))
        return obj(name+'configs','XCConfigurationList',buildConfigurations=ids,defaultConfigurationIsVisible='0',defaultConfigurationName='Release')
    project_configs=configs('project',{})
    ext_configs=configs('extension',{'PRODUCT_BUNDLE_IDENTIFIER':'org.example.ZhuyinBridge.Keyboard','PRODUCT_NAME':'ZhuyinBridgeKeyboard','INFOPLIST_FILE':'KeyboardExtension/Info.plist','GENERATE_INFOPLIST_FILE':'NO','APPLICATION_EXTENSION_API_ONLY':'YES','SKIP_INSTALL':'YES','LD_RUNPATH_SEARCH_PATHS':['$(inherited)','@executable_path/Frameworks','@executable_path/../../Frameworks']})
    ext_target=obj('extTarget','PBXNativeTarget',buildConfigurationList=ext_configs,buildPhases=[sources('extSources',keyboard_sources),frameworks('extFrameworks'),resources('extResources',[privacy])],buildRules=[],dependencies=[],name='ZhuyinBridgeKeyboard',productName='ZhuyinBridgeKeyboard',productReference=ext_product,productType='com.apple.product-type.app-extension')
    proxy=obj('proxy','PBXContainerItemProxy',containerPortal=uid('project'),proxyType='1',remoteGlobalIDString=ext_target,remoteInfo='ZhuyinBridgeKeyboard')
    dependency=obj('dependency','PBXTargetDependency',target=ext_target,targetProxy=proxy)
    embed=obj('embed','PBXCopyFilesBuildPhase',buildActionMask='2147483647',dstPath='',dstSubfolderSpec='13',files=[build('embedExt',ext_product,settings={'ATTRIBUTES':['RemoveHeadersOnCopy']})],name='Embed App Extensions',runOnlyForDeploymentPostprocessing='0')
    app_configs=configs('application',{'PRODUCT_BUNDLE_IDENTIFIER':'org.example.ZhuyinBridge','PRODUCT_NAME':'ZhuyinBridge','INFOPLIST_FILE':'App/Info.plist','GENERATE_INFOPLIST_FILE':'NO','LD_RUNPATH_SEARCH_PATHS':['$(inherited)','@executable_path/Frameworks'],'SWIFT_EMIT_LOC_STRINGS':'YES'})
    app_target=obj('appTarget','PBXNativeTarget',buildConfigurationList=app_configs,buildPhases=[sources('appSources',app_sources),frameworks('appFrameworks'),resources('appResources',[terms,privacy]),embed],buildRules=[],dependencies=[dependency],name='ZhuyinBridge',productName='ZhuyinBridge',productReference=app_product,productType='com.apple.product-type.application')
    project=obj('project','PBXProject',attributes={'LastUpgradeCheck':'1600','TargetAttributes':{app_target:{'CreatedOnToolsVersion':'16.0'},ext_target:{'CreatedOnToolsVersion':'16.0'}}},buildConfigurationList=project_configs,compatibilityVersion='Xcode 14.0',developmentRegion='en',hasScannedForEncodings='0',knownRegions=['en','Base','zh-Hans','zh-Hant'],mainGroup=group,productRefGroup=products,projectDirPath='',projectRoot='',targets=[app_target,ext_target])
    target=ROOT/'ZhuyinBridge.xcodeproj'
    target.mkdir(exist_ok=True)
    (target/'project.pbxproj').write_text('// !$*UTF8*$!\n'+render(dict(archiveVersion='1',classes={},objectVersion='56',objects=objects,rootObject=project))+'\n')
    # Keep a shared app scheme to support the documented xcodebuild command.
    scheme=ET.Element('Scheme',LastUpgradeVersion='1600',version='1.3')
    action=ET.SubElement(scheme,'BuildAction',parallelizeBuildables='YES',buildImplicitDependencies='YES')
    entries=ET.SubElement(action,'BuildActionEntries')
    item=ET.SubElement(entries,'BuildActionEntry',buildForTesting='YES',buildForRunning='YES',buildForProfiling='YES',buildForArchiving='YES',buildForAnalyzing='YES')
    def reference(parent): ET.SubElement(parent,'BuildableReference',BuildableIdentifier='primary',BlueprintIdentifier=app_target,BuildableName='ZhuyinBridge.app',BlueprintName='ZhuyinBridge',ReferencedContainer='container:ZhuyinBridge.xcodeproj')
    reference(item)
    ET.SubElement(scheme,'TestAction',buildConfiguration='Debug',selectedDebuggerIdentifier='Xcode.DebuggerFoundation.Debugger.LLDB',selectedLauncherIdentifier='Xcode.IDEFoundation.Launcher.LLDB',shouldUseLaunchSchemeArgsEnv='YES')
    launch=ET.SubElement(scheme,'LaunchAction',buildConfiguration='Debug',selectedDebuggerIdentifier='Xcode.DebuggerFoundation.Debugger.LLDB',selectedLauncherIdentifier='Xcode.IDEFoundation.Launcher.LLDB',launchStyle='0',useCustomWorkingDirectory='NO',ignoresPersistentStateOnLaunch='NO',debugDocumentVersioning='YES',debugServiceExtension='internal',allowLocationSimulation='YES')
    reference(ET.SubElement(launch,'BuildableProductRunnable',runnableDebuggingMode='0'))
    profile=ET.SubElement(scheme,'ProfileAction',buildConfiguration='Release',shouldUseLaunchSchemeArgsEnv='YES',savedToolIdentifier='',useCustomWorkingDirectory='NO',debugDocumentVersioning='YES')
    reference(ET.SubElement(profile,'BuildableProductRunnable',runnableDebuggingMode='0'))
    ET.SubElement(scheme,'AnalyzeAction',buildConfiguration='Debug')
    ET.SubElement(scheme,'ArchiveAction',buildConfiguration='Release',revealArchiveInOrganizer='YES')
    folder=target/'xcshareddata/xcschemes';folder.mkdir(parents=True,exist_ok=True)
    ET.indent(scheme)
    ET.ElementTree(scheme).write(folder/'ZhuyinBridge.xcscheme',encoding='utf-8',xml_declaration=True)
    base={'CFBundleDevelopmentRegion':'$(DEVELOPMENT_LANGUAGE)','CFBundleExecutable':'$(EXECUTABLE_NAME)','CFBundleIdentifier':'$(PRODUCT_BUNDLE_IDENTIFIER)','CFBundleInfoDictionaryVersion':'6.0','CFBundleName':'$(PRODUCT_NAME)','CFBundleShortVersionString':'$(MARKETING_VERSION)','CFBundleVersion':'$(CURRENT_PROJECT_VERSION)'}
    app={**base,'CFBundleDisplayName':'注音桥','CFBundlePackageType':'APPL','LSRequiresIPhoneOS':True,'UILaunchScreen':{},'UIApplicationSceneManifest':{'UIApplicationSupportsMultipleScenes':False},'UISupportedInterfaceOrientations':['UIInterfaceOrientationPortrait','UIInterfaceOrientationLandscapeLeft','UIInterfaceOrientationLandscapeRight'],'UISupportedInterfaceOrientations~ipad':['UIInterfaceOrientationPortrait','UIInterfaceOrientationPortraitUpsideDown','UIInterfaceOrientationLandscapeLeft','UIInterfaceOrientationLandscapeRight']}
    extension={**base,'CFBundleDisplayName':'注音桥 · 拼音提示','CFBundlePackageType':'XPC!','NSExtension':{'NSExtensionPointIdentifier':'com.apple.keyboard-service','NSExtensionPrincipalClass':'$(PRODUCT_MODULE_NAME).KeyboardViewController','NSExtensionAttributes':{'IsASCIICapable':True,'PrefersRightToLeft':False,'PrimaryLanguage':'zh-Hant','RequestsOpenAccess':False}}}
    privacy={'NSPrivacyTracking':False,'NSPrivacyTrackingDomains':[],'NSPrivacyCollectedDataTypes':[],'NSPrivacyAccessedAPITypes':[]}
    for path,data in [('App/Info.plist',app),('KeyboardExtension/Info.plist',extension),('PrivacyInfo.xcprivacy',privacy)]:
        (ROOT/path).write_bytes(plistlib.dumps(data,sort_keys=False))
    print('Generated Xcode project, app scheme, Info.plist files and privacy manifest.')

if __name__=='__main__': main()
