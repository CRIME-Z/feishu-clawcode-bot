from setuptools import setup, find_packages

setup(
    name="feishu-clawcode-bot",
    version="1.0.0",
    description="飞书机器人 + ClawCode AI 对话",
    author="Your Name",
    author_email="your@email.com",
    url="https://github.com/yourname/feishu-clawcode-bot",
    packages=find_packages(),
    install_requires=[
        "flask>=3.0.0",
        "requests>=2.31.0",
        "python-dotenv>=1.0.0",
    ],
    extras_require={
        "dev": [
            "pytest>=8.0.0",
        ]
    },
    python_requires=">=3.12",
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3.12",
    ],
    license="MIT",
)
