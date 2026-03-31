import sys
import os
import copy
import shutil
import json
import argparse
import subprocess
import warnings
warnings.filterwarnings('ignore')

from pathlib import Path

from utilskit.versionutils import version_up, git_addcommit
from utilskit.hashutils import hashlist2hash, file2hash
from utilskit.timeutils import get_now


# [2.5.0] @done_log: 신규 함수 `lock_update 추가`
def lock_update(lock_info, hash_cache, new_b_version, p_version, now):
    # lock 의 빌드 버전 갱신
    lock_info["build"]["version"] = new_b_version
    lock_info["build"]["match"] = p_version
    lock_info["build"]["time"] = now

    whole_hash_list = []
    c_info_list = lock_info["component"]
    for c_info in c_info_list:
        c_name = c_info["name"]
        do_build = c_info["build"]
        c_mode = c_info["mode"]
        c_path = c_info["path"]

        # 빌드 대상 여부 파악
        if not do_build:
            continue
        
        if c_mode == "file_group":
            c_hash_dict = hash_cache.get(f"{c_path}/{c_name}")
        else:
            c_hash_dict = hash_cache.get(c_path)
        
        if not c_hash_dict is None:
            whole_hash_list += list(c_hash_dict.values())

    # 통합 해시 계산
    product_hash = hashlist2hash(whole_hash_list)
    lock_info["product"]["hash"] = product_hash

    # 해시 스키마 버전 입력
    schema_version = hash_cache["schema_version"]
    lock_info["product"]["hash_schema_version"] = schema_version
    return lock_info


# [2.5.0] @done_log: 프로덕트 통합 해시를 lock에 추가
def staging(now, product_path, stage_path):

    # 해시 캐시 불러오기
    with open(product_path / ".hash_cache.json", "r", encoding="utf-8-sig") as f:
        hash_cache = json.load(f)
    
    # lock 불러오기
    with open(product_path / "product.lock", "r", encoding="utf-8-sig") as f:
        lock_info = json.load(f)
    s_name = lock_info["product"]["name"]
    
    # ==============================================
    # [2.5.0] @done_log: timeout 방식 대신 exit code 활용
    print("현재 파일 해시 검증 중...")
    dev_path = product_path.parent / "dev_tools"
    cmd = ["python", "-m", "versioning", "--check-only", "--name", s_name]
    result = subprocess.run(
        cmd, 
        cwd=dev_path, 
        capture_output=True, 
        text=True
    )
    if result.returncode == 1:
        raise TimeoutError("파일 해시에 변동이 있습니다. versioning 을 먼저 진행해야합니다.")
    
    # ====================================================================
    # lock 의 빌드 버전 갱신
    p_version = lock_info["product"]["version"]
    pre_b_version = lock_info["build"]["version"]
    new_b_version, b_tag = version_up("빌드", pre_b_version)

    # lock 값 업데이트
    lock_info = lock_update(
        lock_info=lock_info, 
        hash_cache=hash_cache, 
        new_b_version=new_b_version, 
        p_version=p_version, 
        now=now
    )

    # lock 저장
    with open(product_path / "product.lock", "w", encoding="utf-8-sig") as f:
        json.dump(lock_info, f, indent='\t', ensure_ascii=False)
    # 아카이브에도 저장
    with open(product_path / "archive" / f"product_v{p_version}.lock", "w", encoding="utf-8-sig") as f:
        json.dump(lock_info, f, indent='\t', ensure_ascii=False)
        
    # lock 을 git commit 진행
    git_addcommit(product_path, f'*{b_tag}: {get_now("년-월-일 시:분:초")} ver {new_b_version} building')
    
    # =============================================================
    # 기존 staging 폴더 삭제
    if os.path.exists(stage_path):
        shutil.rmtree(stage_path)
    os.makedirs(stage_path, exist_ok=True)
    
    # stage 진행
    c_info_list = lock_info["component"]
    common_exclude = lock_info["product"]["exclude"]
    for c_info in c_info_list:
        c_name = c_info["name"]
        # c_version = c_info["version"]
        do_build = c_info["build"]
        c_mode = c_info["mode"]
        c_path = c_info["path"]
        c_include = c_info["include"]
        # c_bundle = c_info["bundle"]
        c_exclude = c_info["exclude"]

        # 빌드 대상 여부 파악
        if not do_build:
            continue

        if c_mode == "dir":
            # src, tgt 설정
            src = c_path
            rel_path = Path(c_path).relative_to(product_path)
            tgt = stage_path / rel_path
            print(src, tgt)
            
            # 새 폴더 전송(제외 목록이 없는 경우)
            ignore_list = c_exclude + common_exclude
            if len(ignore_list) == 0:
                shutil.copytree(src, tgt)
            # 새 폴더 전송(제외 목록이 존재하는 경우)
            else:
                shutil.copytree(src, tgt,
                    ignore=shutil.ignore_patterns(*ignore_list)
                )
        # [2.5.12] @done_log: file_group staging 시 버전 명세서도 옮겨지도록 적용
        elif c_mode == "file_group":
            
            # 버전 명세서 별 진행
            for ver_name in [c_name, "__version__.py"]:
                # src, tgt 설정
                version_src = Path(c_path) / ver_name
                version_tgt = stage_path / ver_name
                # 기존 staging 파일 삭제
                if os.path.exists(version_tgt):
                    os.remove(version_tgt)
                # 새 파일 전송
                shutil.copy2(version_src, version_tgt)

            # include 파일 별 진행
            for inc in c_include:
                src = Path(c_path) / inc
                tgt = stage_path / inc
                if os.path.exists(tgt):
                    os.remove(tgt)
                shutil.copy2(src, tgt)

    print("대상 컴포넌트 전체 빌드 성공")
    

# [2.5.0] @done_log: stage 해시를 검증하는 부분 추가
def release(product_path, dist_path, stage_path, release_path):
    
    # stage lock 불러오기
    with open(stage_path / "product.lock", "r", encoding="utf-8-sig") as f:
        lock_info = json.load(f)
    p_name = lock_info["product"]["name"]

    # hash_cache 불러오기
    with open(stage_path / ".hash_cache.json", "r", encoding="utf-8-sig") as f:
        hash_cache = json.load(f)

    # 컴포넌트별 해시 검증 진행
    comp_info_list = lock_info["component"]
    for c_info in comp_info_list:
        c_name = c_info["name"]
        c_mode = c_info["mode"]
        c_path = c_info["path"]
        do_build = c_info["build"]

        # 빌드 대상이 아닌 경우
        if not do_build:
            continue

        # dist/stage 를 경로에 추가
        dist_c_path = Path(c_path.replace(p_name, f"{p_name}/dist/stage"))

        # 파일군인 경우 경로 올리기
        if c_mode in "file_group":
            c_path = str(Path(c_path) / c_name)
            # dist_c_path = str(dist_c_path.parent)
            # key = str(Path(c_path).parent)

        print(c_path)
        # 해시 캐시 파일별 진행
        for f_name, cache_f_hash in hash_cache[c_path].items():
            f_path = str(dist_c_path / f_name)
            # 파일의 현재 해시값 추출
            try:
                f_hash = file2hash(f_path)
            # 캐시된 파일이 stage 에 없는 경우
            except FileNotFoundError:
                print(f"[Error] 무결성 검증 실패 : 구성 파일 누락")
                print(f"hash cache 에 등록된 파일({f_path})이 실제 경로에 존재하지 않습니다.")
                print("stage 가 손상되었을 가능성이 있기에 release 를 취소합니다.")
                return
            
            # 현재 해시와 캐시 해시 비교
            try:
                if f_hash != cache_f_hash:
                    raise ValueError()
            except ValueError:
                print(f"[Error] 무결성 검증 실패 : 해시 불일치")
                print(f"hash cache 에 등록된 파일({f_path})의 해시값이 현재 해시 값과 일치하지 않습니다.")
                print("stage 가 손상되었거나 해시 계산로직의 변경 가능성이 있기에 release 를 취소합니다.")
                return
    print(">>> stage 해시에 이상이 없으므로 release 를 진행합니다")
    
    # 이름, 버전
    p_version = lock_info["product"]["version"]
    b_version = lock_info["build"]["version"]

    # ===========================================================================
    # tar.gz 생성
    tar_name = f'{p_name}_v{p_version}-b{b_version}.tar.gz'

    print(f"배포 {tar_name} 생성")
    if os.path.exists(release_path / tar_name):
        print(f'{tar_name} --> 이미 release 된 버전입니다')
        sys.exit()
    else:
        # 기존 release 파일 전부 삭제
        pre_release = os.listdir(release_path)
        for pr in pre_release:
            os.remove(release_path / pr)
        
        # 새로운 release 생성 & archiving
        cmd = f"""
        cd {dist_path} && \
        tar -czf {release_path / tar_name} --transform='s,^stage/,{p_name}/,' stage/ && \
        cp {release_path / tar_name} {str(product_path / 'archive') + '/'}
        """
        subprocess.run(cmd, shell=True, check=True)
        print(f"{tar_name} release & archive 완료")

    # ===========================================================================
    # docker 생성
    docker_image = f"{p_name}:b{b_version}"
    print(f"docker 이미지 {docker_image} 생성")
    cmd = f"""
        cd {product_path} && \
        docker build -t {docker_image} .
        """
    subprocess.run(cmd, shell=True, check=True)
    
    # docker 이미지 압축
    print(f"docker 이미지 압축&추출")
    cmd = f"""
    cd {release_path} && \
    docker save {p_name}:b{b_version} | pv | gzip > {p_name}_b{b_version}_doc.tar.gz 
    """
    subprocess.run(cmd, shell=True, check=True)


def build(env):
    scripts_path = Path(__file__).resolve().parent
    product_path = scripts_path.parent
    dist_path = product_path / "dist"

    now = get_now("년-월-일 시:분:초")

    # staging 빌드인 경우
    stage_path = dist_path / "stage"
    release_path = dist_path / "release"
    if env == 'stage':
        staging(now, product_path, stage_path)
    # releas 빌드인 경우
    elif env == 'release':
        release(
            product_path=product_path,
            dist_path=dist_path,
            stage_path=stage_path,
            release_path=release_path
        )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--env', type=str, required=True)
    args = parser.parse_args()
    env = args.env
    build(env)

if __name__ == "__main__":
    main()
