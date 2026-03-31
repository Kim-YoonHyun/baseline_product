import os
import sys
import json
import shutil
import tomlkit
import subprocess
import configparser
from pathlib import Path


USER_PATH = Path("~").expanduser()
sys.path.insert(0, str(USER_PATH / "library" / "utilskit" / "src"))
sys.path.insert(0, str(USER_PATH / "library" / "logie" / "src"))
from utilskit.versionutils import version_up, git_addcommit
from utilskit.timeutils import get_now


def main():
    scripts_path = Path(__file__).resolve().parent
    product_path = scripts_path.parent
    lib_path = product_path.parent
    dist_path = product_path / "dist"
    dev_path = lib_path / "dev_tools"

    # lock 파일 불러오기
    with open(product_path / "product.lock", "r", encoding="utf-8-sig") as f:
        lock_info = json.load(f)
    
    # pyproject.toml 불러오기
    with open(product_path / "pyproject.toml", "r", encoding="utf-8-sig") as f:
        contents = f.read()
        toml_info = tomlkit.parse(contents)
    
    p_name = lock_info["product"]["name"]
    c_info_list = lock_info["component"]

    # versioning 실행 여부 파악 = 해시 변동 있는지 파악
    dev_path = product_path.parent / "dev_tools"
    cmd = ["python", "-m", "versioning", "--check-only", "--name", p_name]
    result = subprocess.run(
        cmd, 
        cwd=dev_path, 
        capture_output=True, 
        text=True
    )
    if result.returncode == 1:
        raise TimeoutError("파일 해시에 변동이 있습니다. versioning 을 먼저 진행해야합니다.")

    # 빌드 버전 업 & 매칭
    p_version = lock_info["product"]["version"]
    pre_b_version = lock_info["build"]["version"]
    new_b_version, tag = version_up(p_name, pre_b_version)
    lock_info["build"]["version"] = new_b_version
    lock_info["build"]["match"] = p_version
    with open(product_path / "product.lock", "w", encoding="utf-8-sig") as f:
        json.dump(lock_info, f, indent="\t", ensure_ascii=False)
    # 아카이브 파일도 변환
    with open(product_path / "archive" / f"product_v{p_version}.lock", "w", encoding="utf-8-sig") as f:
        json.dump(lock_info, f, indent="\t", ensure_ascii=False)

    # toml 버전 업
    # [1.1.3] @done_log: toml encoding 을 utf-8-sig 에서 utf-8 로 변경
    toml_info["project"]["version"] = new_b_version
    with open(product_path / "pyproject.toml", "w", encoding="utf-8") as f:
        f.write(toml_info.as_string())
    
    # 컴포넌트별 dist 로 옮김
    common_exclude = lock_info["product"]["exclude"]
    for c_info in c_info_list:
        c_name = c_info["name"]
        do_build = c_info["build"]
        c_mode = c_info["mode"]
        c_path = c_info["path"]
        c_exclude = c_info["exclude"]

        if not do_build:
            continue

        if c_mode == "dir":
            rel_path = Path(c_path).relative_to(product_path)
            tgt_path = dist_path / rel_path
            # 기존 staging 폴더 삭제
            if os.path.exists(tgt_path):
                shutil.rmtree(tgt_path)

            # 새 폴더 전송(제외 목록이 없는 경우)
            ignore_list = c_exclude + common_exclude
            if len(ignore_list) == 0:
                shutil.copytree(c_path, tgt_path)

            # 새 폴더 전송(제외 목록이 존재하는 경우)
            else:
                shutil.copytree(c_path, tgt_path,
                    ignore=shutil.ignore_patterns(*ignore_list)
                )
        elif c_mode == "file_group":
            file_list = c_info["include"]
            for file_name in file_list:
                # src, tgt 설정
                src = Path(c_path) / file_name
                tgt = Path(dist_path) / file_name

                # 기존 staging 파일 삭제
                if os.path.exists(tgt):
                    os.remove(tgt)

                # 새 파일 전송(manifest 제외)
                shutil.copy2(src, tgt)
    
    # [1.1.6] @done_log: 끝나고 전체 git commit 부분 추가
    git_addcommit(product_path, f'*{tag}: {get_now("년-월-일 시:분:초")} ver {new_b_version} building')

    # token.ini 읽기
    config = configparser.ConfigParser()
    config.read(os.path.join(lib_path, "token.ini"))

    username = config['PyPI']['username']
    password = config['PyPI']['password']

    # subprocess 로 build 실행
    # [1.1.1] @done_log: 작업 디렉토리를 product_path 에서 dist_path 로 변경
    subprocess.run(["python", "-m", "build"], cwd=dist_path)

    # subprocess 로 twine upload 실행
    subprocess.run([
        'twine', 'upload', f'{dist_path}/dist/*',
        '-u', username,
        '-p', password
    ])
    

if __name__ == "__main__":
    main()