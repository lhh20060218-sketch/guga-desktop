"""Add the existing sidecar runtimes, produce a standard per-user installer."""
import json,shutil,subprocess,hashlib,uuid,os,sys
from pathlib import Path
import yaml
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'release-private/2026.11.1.1';APP=OUT/'Guga';VENDOR=ROOT/'build/private-test/vendor'

def prepare_sidecar():
    VENDOR.mkdir(parents=True,exist_ok=True)
    dsh=Path.home()/'.local/bin/node_modules/@deepseek-ai/dsh'
    shutil.copytree(dsh,VENDOR/'dsh',dirs_exist_ok=True)
    shutil.copy2(shutil.which('node'),VENDOR/'node.exe')
    home=VENDOR/'dsh-home';profile=home/'profiles/headless';profile.mkdir(parents=True,exist_ok=True)
    source=Path.home()/'.dsh/profiles/headless'
    for name in ('cordis.yml','cordis.patch.yml','package.json','pnpm-workspace.yaml'):
        shutil.copy2(source/name,profile/name)
    # Preserve the provider adapter overlay that was verified on this machine.
    # It contains provider routing only; the API key comes from the environment.
    shutil.copy2(Path.home()/'.dsh/cordis.patch.yml',home/'cordis.patch.yml')

def installer():
    text='''咕嘎桌宠 私人测试版 2026.11.1.2

安装后打开桌宠，右键开启长语音。无需安装 Python、Node 或配置 API。
说“给我唱首歌吧”默认播放咕嘎翻唱《晴天》，戴墨镜并摇摆；约75秒暂停互动，说“继续唱歌”继续。停止/结束会摘掉墨镜。
普通语音保留 Edge TTS；实时通话为千问 Qwen-Audio-3.1-Realtime；内部推理和工具执行为 OpenCode Go DeepSeek V4.1 Flash。
可以打开网页、看窗口截图、操作软件、组织文字并在指定微信会话发送。微信及其他目标软件需要在接收者电脑上自行安装并登录。
模型服务需要联网；本测试包已按作者授权预填两家密钥，会使用作者账户的套餐/免费额度。免费额度用完即停由服务端账户设置保障。
此包包含可读取的测试凭据，仅限指定测试者，请勿公开上传或转发。正式发布应更换为用户自行配置或受控服务端授权。
包中不含作者聊天记录、录音、声纹、浏览器登录态或私人软件路径。软件按需观察目标窗口，不是持续录像。
唱歌时外放模式暂停收音避免回声，每75秒停下交流；耳机模式可以边唱边说。
大肥鱼已移植 dsh-pet 原版透明动作与独立播放器；拖拽桌宠为普通移动，不会甩抛或剧烈摇晃。
咕嘎新增“开心摆鳍舞”：右键点开音乐与动作，或直接对咕嘎说“跳舞”。动作采用单一原画部件形变，避免插帧叠影。
已进行自动回归和本机打包运行检查；不同Windows、声卡、微信版本仍需实际验收。未对歌曲音色主观质量作保证。
卸载程序会移除程序文件；若保留runtime目录，里面是本机使用期间生成的数据，可自行备份。
'''
    (APP/'使用说明.txt').write_text(text,encoding='utf-8-sig')
    script=f'''[Setup]
AppId=GugaPenguinPetPrivateTest
AppName=咕嘎桌宠（测试版）
AppVersion=2026.11.1.2
DefaultDirName={{localappdata}}\\Programs\\GugaPetTest
DefaultGroupName=咕嘎桌宠
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir={OUT}
OutputBaseFilename=Guga-Setup-2026.11.1.2-private
Compression=zip
SolidCompression=no
WizardStyle=modern
DisableProgramGroupPage=yes
UninstallDisplayIcon={{app}}\\Guga.exe
InfoBeforeFile={APP/'使用说明.txt'}
[Files]
Source: "{APP}\\*"; DestDir: "{{app}}"; Flags: ignoreversion recursesubdirs createallsubdirs; Excludes: "startup.log,pet_debug.log,pet_3d.log,*.sqlite3,*.sqlite3-*,runtime\\dsh-home\\*,vendor\\pwsh\\*,vendor\\dsh\\node_modules\\**\\src\\*,vendor\\dsh\\node_modules\\**\\test\\*,vendor\\dsh\\node_modules\\**\\tests\\*,vendor\\dsh\\node_modules\\**\\docs\\*,vendor\\dsh\\node_modules\\**\\*.md,vendor\\dsh\\node_modules\\**\\*.ts,vendor\\dsh\\node_modules\\**\\*.d.ts,vendor\\dsh\\node_modules\\**\\*.d.mts,vendor\\dsh\\node_modules\\**\\*.map,vendor\\dsh\\node_modules\\**\\*.tsbuildinfo"
[Icons]
Name: "{{group}}\\咕嘎桌宠"; Filename: "{{app}}\\Guga.exe"
Name: "{{userdesktop}}\\咕嘎桌宠"; Filename: "{{app}}\\Guga.exe"
[Run]
Filename: "{{app}}\\Guga.exe"; Description: "启动咕嘎桌宠"; Flags: nowait postinstall skipifsilent
'''
    path=OUT/'Guga-Setup.iss';path.write_text(script,encoding='utf-8-sig')
    compiler=ROOT/'runtime/build-tools/Inno7/ISCC.exe'
    with (OUT/'installer-build.log').open('w',encoding='utf-8') as log:
        r=subprocess.run([str(compiler),str(path)],stdout=log,stderr=subprocess.STDOUT,timeout=900)
    if r.returncode:raise RuntimeError('Installer compilation failed; inspect installer-build.log')
    exe=OUT/'Guga-Setup-2026.11.1.2-private.exe'
    (OUT/'SHA256.txt').write_text(hashlib.sha256(exe.read_bytes()).hexdigest()+'  '+exe.name+'\n',encoding='ascii')
    print(json.dumps(dict(ok=True,installer=str(exe),bytes=exe.stat().st_size)))

if __name__=='__main__':
    if '--stage-sidecar' in sys.argv:
        prepare_sidecar();print('sidecar staged');sys.exit(0)
    if not (APP/'Guga.exe').is_file():raise RuntimeError('Standalone build not ready')
    if not (VENDOR/'node.exe').is_file():prepare_sidecar()
    def link(source,destination):
        src='\\\\?\\'+str(Path(source).resolve());dst='\\\\?\\'+str(Path(destination).resolve())
        if os.path.exists(dst) and os.path.samefile(src,dst):return destination
        try:os.link(src,dst)
        except OSError:shutil.copy2(src,dst)
        return destination
    shutil.copytree(VENDOR,APP/'vendor',copy_function=link,dirs_exist_ok=True)
    installer()
