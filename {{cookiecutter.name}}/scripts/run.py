import sys
import os
import json
import ast
import runpy
import argparse
from pathlib import Path
from packaging.specifiers import SpecifierSet
from packaging.version import Version
from packaging import version



def get_requires(name, info):

    # 버전 요구사항 추출
    comp_info_list = info["component"]
    for comp_info in comp_info_list:
        c_name = comp_info["name"]
        if name == c_name:
            break
    requires = comp_info["requires"]

    return requires


def get_version(file_path):
    with open(file_path, 'r') as f:
        tree = ast.parse(f.read())
        
    for node in tree.body:
        if isinstance(node, ast.Assign):
            # 변수 이름이 __version__인지 확인
            target_name = node.targets[0].id if isinstance(node.targets[0], ast.Name) else ""
            if target_name == "__version__":
                # 값(문자열)을 반환
                return ast.literal_eval(node.value)
    return None


# [2.5.13] @done_log: `verify_integrity` 함수의 내부 리펙토링 진행
def verify_integrity(name, env, run_ver, product_path, manifest, lock_info):

    # 요구 컴포넌트 정보 추출
    if env == "dev":
        requires = get_requires(name, manifest)
    elif env in ["stage", "release"]:
        # 검증 & 운영시 스냅샷 버전 비교
        run_lock_ver = lock_info["product"]["resolved"][name]
        if version.parse(run_ver) != version.parse(run_lock_ver):
            raise ValueError(f"{name} 의 버전({run_ver}) 이 스냅샷의 버전({run_lock_ver}) 과 맞지 않습니다.")
        requires = get_requires(name, lock_info)

    resolved = lock_info["product"]["resolved"]
    for req_comp, req_ver in requires.items():
        # 요구 컴포넌트의 현재 버전값
        try:
            curr_ver = get_version(product_path / req_comp / "__version__.py")
        except Exception:
            curr_ver = get_version(product_path / req_comp)
            
        # 요구 컴포넌트의 현재 버전과 요구사항 버전 비교
        """
        requires 와의 비교를 통해 실시간 컴포넌트 상태 자체가 버전을 만족하는지 검증
        """
        is_satisfied = Version(curr_ver) in SpecifierSet(req_ver)
        if not is_satisfied:
            raise ValueError(f"{req_comp} 의 현재 버전({curr_ver})이 요구 버전({req_ver})과 맞지 않습니다.")
        
        # 대상 컴포넌트의 lock 버전 값
        lock_ver = resolved.get(req_comp)
        """
        .lock 과의 비교를 통해 각 컴포넌트의 현재 스냅샷이 버전값이 동일한지 검증
        개발(dev) 상태인 경우 스냅샷 자체가 존재하지 않으므로 무일치 시 경고만 출력
        """
        if lock_ver is None:
            string = f"요구 컴포넌트의 명칭({req_comp})이 .lock 에 존재하지 않습니다. 컴포넌트의 이름을 확인하십시오."
            if env == "dev":
                print(f"|경고| {string}")
            elif env in ["stage", "release"]:
                raise ValueError(string)
        if version.parse(curr_ver) != version.parse(lock_ver):
            string = f"요구 컴포넌트의 현재 버전({curr_ver}) 이 스냅샷 버전 ({lock_ver}) 과 일치하지 않습니다."
            if env == "dev":
                print(f"|경고| {string}")
            elif env in ["stage", "release"]:
                raise ValueError(string)
            

# [2.5.13] @done_log: 컴포넌트 실행용 함수 `run_component` 
def run_component(args, unknown_args):

    name = args.name
    env = args.env
    # run_mode = args.run_mode
    # role = args.role
    # local = args.local
    # engine_ = args.engine

    # 경로
    scripts_path = Path(__file__).resolve().parent
    product_path = scripts_path.parent
    src_path = product_path / "src"

    # manifest.json 불러오기
    with open(product_path / "manifest.json", "r", encoding="utf-8-sig") as f:
        manifest = json.load(f)
    
    # product.lock 불러오기
    with open(product_path / "product.lock", "r", encoding="utf-8-sig") as f:
        lock_info = json.load(f)

    # src 가 위치하고 있는 path 추가
    if src_path not in sys.path:
        sys.path.insert(0, str(src_path))
    
    # 소스코드
    run_path = src_path / name / "run.py"

    # run.py 존재 여부 확인
    if not os.path.isfile(run_path):
        raise FileNotFoundError(f"실행용 run.py 파일이 해당 모듈({name})에 존재하지 않거나 해당 모듈 자체가 존재하지 않습니다.")
    
    # 소스코드 버전
    run_ver = get_version(src_path / name / "__version__.py")

    # 버전 정합성 비교
    verify_integrity(name, env, run_ver, product_path, manifest, lock_info)

    # # [2.6.0] @done_log: role 추가
    # if local:
    #     sys.argv = [str(run_path), "--env", env, "--run_mode", run_mode, "--role", role, "--engine", engine_, "--local"]
    # else:
    #     sys.argv = [str(run_path), "--env", env, "--run_mode", run_mode, "--role", role, "--engine", engine_]
    # runpy.run_module(f"{name}.run", run_name="__main__")

    # [2.7.1] @done_log: sys.argv 재구성 시, 하위 모듈로 나머지 인자(unknown_args)를 그대로 전달하도록 변경
    sys.argv = [str(run_path), "--env", env] + unknown_args
    runpy.run_module(f"{name}.run", run_name="__main__")


def main():

    # 경로 설정 (현재 스크립트 위치 기준)
    current_dir = Path(__file__).resolve().parent
    project_root = current_dir.parent
    src_path = project_root / "src"


    parser = argparse.ArgumentParser()
    # scripts 단에서 필요한 최소한의 인자만 정의
    parser.add_argument("--name", type=str, required=True)
    parser.add_argument('--env', required=True)
    # parser.add_argument('--run_mode', default='normal')
    # parser.add_argument("--role", type=str, choices=['producer', 'consumer'], required=True, help="컨테이너의 역할 (반장 or 작업자)")
    # parser.add_argument('--local', action="store_true")
    # parser.add_argument("--engine", type=str, choices=['k8s', 'docker'], required=True)
    # args = parser.parse_args()
    # [2.7.1] @done_log: parse_known_args()를 사용하여 정의되지 않은 나머지 인자들을 unknown_args 리스트에 담음
    """
    예: python run_scripts.py --name moduleA --env dev --role producer --local
    -> args: namespace(name='moduleA', env='dev')
    -> unknown_args: ['--role', 'producer', '--local']
    """
    args, unknown_args = parser.parse_known_args()
    
    run_component(args, unknown_args)


if __name__ == "__main__":
    main()
