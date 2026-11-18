FROM modelscope-registry.cn-beijing.cr.aliyuncs.com/modelscope-repo/python:3.10

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /home/user/app
COPY . /home/user/app

# 魔搭构建环境在国内，优先走阿里云 PyPI 镜像
RUN pip install -r requirements.txt -i https://mirrors.aliyun.com/pypi/simple/ \
    || pip install -r requirements.txt

EXPOSE 7860

# 魔搭 Docker 创空间固定使用 7860 端口，且必须监听 0.0.0.0
CMD ["uvicorn", "travel_advisor.app:app", "--host", "0.0.0.0", "--port", "7860"]
