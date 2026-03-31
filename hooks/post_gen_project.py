import os
import shutil

project_type = "{{ cookiecutter.type }}"
project_name = "{{ cookiecutter.name }}"


# 삭제 로직을 함수화하여 중복 제거 및 가독성 향상
def remove_path(path):
    if not os.path.exists(path):
        return  # 경로가 없으면 그냥 종료
    try:
        if os.path.isdir(path):
            shutil.rmtree(path)
        else:
            os.remove(path)
    except Exception as e:
        print(f"Error removing {path}: {e}")


# 1. 공통 타겟 설정 (선택 사항)
targets = []

# 2. 타입별 타겟 추가
if project_type == 'package':
    targets = [
        os.path.join('configs', 'dev'),
        os.path.join('configs', 'release'),
        os.path.join('configs', 'stage'),
        os.path.join('dist', 'release'),
        os.path.join('dist', 'stage'),
        os.path.join("scripts", "run.py"),
        os.path.join("scripts", "build.py"),
        os.path.join("scripts", "test_build.sh"),
        os.path.join(".dockerignore"),
        os.path.join("Dockerfile")
    ]
elif project_type == "system":
    targets = [
        os.path.join('docs', 'def_base.md'),
        os.path.join('scripts', 'sync_dependencies.py'),
        os.path.join('scripts', 'upload.py'),
        os.path.join("src", project_name),
        os.path.join("src", "test"),
        os.path.join("pyproject.toml")
    ]

# 3. 일괄 삭제 실행
for target in targets:
    remove_path(target)