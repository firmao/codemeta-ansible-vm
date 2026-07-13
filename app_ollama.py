import os
import tempfile
import json
import requests
import re
from git import Repo

def extract_exact_packages(tmp_dir, target_files):
    """
    Scans the repository globally using file extensions and manifest rules
    to capture all programming languages, runtimes, and build tools.
    """
    packages = {"apt": set(), "pip": set(), "npm": set(), "r": set()}
    
    # Track detected languages via files to catch languages without explicit manifests
    detected_extensions = {
        '.py': 'python3',
        '.r': 'r-base',
        '.R': 'r-base',
        '.js': 'nodejs',
        '.ts': 'nodejs',
        '.c': 'gcc',
        '.cpp': 'g++',
        '.cc': 'g++',
        '.pl': 'swi-prolog', # Common for Prolog repositories
        '.sh': 'bash',
        '.java': 'default-jdk',
        '.go': 'golang',
        '.rs': 'rustc'
    }

    for root, _, files in os.walk(tmp_dir):
        for file in files:
            file_path = os.path.join(root, file)
            _, ext = os.path.splitext(file)
            
            # Detect based on file extensions
            if ext in detected_extensions:
                packages["apt"].add(detected_extensions[ext])
                
            # Scan for generic build systems
            if file == "Makefile" or file == "CMakeLists.txt":
                packages["apt"].add("build-essential")
            if file == "configure":
                packages["apt"].add("autoconf")
                packages["apt"].add("make")

            if file not in target_files:
                continue
            
            try:
                with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read()
                
                # 1. Python parsing
                if file in ["requirements.txt", "setup.py", "pyproject.toml"]:
                    matches = re.findall(r'^[a-zA-Z0-9_\-\[\]]+', content, re.MULTILINE)
                    for match in matches:
                        if match.lower() not in ["python", "pip", "setuptools"]:
                            packages["pip"].add(match.strip())
                            
                # 2. Node parsing
                elif file == "package.json":
                    data = json.loads(content)
                    deps = {**data.get("dependencies", {}), **data.get("devDependencies", {})}
                    for dep in deps.keys():
                        packages["npm"].add(dep)
                        
                # 3. R parsing
                elif file == "DESCRIPTION":
                    sections = re.findall(r'(?:Imports|Depends|Suggests):\s*([^Configuration|System|Description|License]+)', content, re.DOTALL)
                    for section in sections:
                        clean_pkgs = re.findall(r'[a-zA-Z0-9\.]+', section)
                        for pkg in clean_pkgs:
                            if pkg not in ["R", "Imports", "Depends", "Suggests"]:
                                packages["r"].add(pkg)
                                
                # 4. CodeMeta parsing
                elif file == "codemeta.json":
                    data = json.loads(content)
                    reqs = data.get("softwareRequirements", []) or data.get("targetProduct", {}).get("softwareRequirements", [])
                    if isinstance(reqs, list):
                        for req in reqs:
                            if isinstance(req, str):
                                packages["apt"].add(req.split()[0])
                            elif isinstance(req, dict) and "name" in req:
                                packages["apt"].add(req["name"])
                                
                # 5. Readme parsing
                if file.lower() == "readme.md":
                    system_tools = ["docker", "docker-compose", "git", "gdal-bin", "libgdal-dev", "libproj-dev", "libgeos-dev", "postgresql", "redis", "tesseract-ocr"]
                    for tool in system_tools:
                        if tool in content.lower():
                            packages["apt"].add(tool)
            except Exception:
                pass
                
    return {k: sorted(list(v)) for k, v in packages.items()}

def generate_fast_ansible(repo_url: str, model_name: str = "llama3.2:1b"):
    ollama_url = "http://127.0.0.1:11434/api/generate"
    
    try:
        requests.get("http://127.0.0.1:11434", timeout=3)
    except requests.exceptions.ConnectionError:
        return

    with tempfile.TemporaryDirectory() as tmp_dir:
        try:
            Repo.clone_from(repo_url, tmp_dir, depth=1)
        except Exception:
            return

        target_files = ["requirements.txt", "codemeta.json", "package.json", "DESCRIPTION", "setup.py", "pyproject.toml", "readme.md", "README.md", "environment.yml"]
        
        # Pull software signatures via the improved global heuristic scanner
        discovered_software = extract_exact_packages(tmp_dir, target_files)
        
        # Inject matching runtimes logically
        if discovered_software["pip"] and "python3-pip" not in discovered_software["apt"]:
            discovered_software["apt"].append("python3-pip")
        if discovered_software["npm"] and "nodejs" not in discovered_software["apt"]:
            discovered_software["apt"].append("nodejs")
        if discovered_software["r"] and "r-base" not in discovered_software["apt"]:
            discovered_software["apt"].append("r-base")
        if not discovered_software["apt"]:
            discovered_software["apt"].append("build-essential")

        requirement_summary = ""
        if discovered_software["apt"]:
            requirement_summary += f"APT/System Packages: {', '.join(discovered_software['apt'])}\n"
        if discovered_software["pip"]:
            requirement_summary += f"Python PIP Packages: {', '.join(discovered_software['pip'])}\n"
        if discovered_software["npm"]:
            requirement_summary += f"Node NPM Packages: {', '.join(discovered_software['npm'])}\n"
        if discovered_software["r"]:
            requirement_summary += f"R Language Packages: {', '.join(discovered_software['r'])}\n"

        prompt = f"""
        You are a deterministic YAML writer. Convert this explicit list of software applications directly into an Ansible playbook:
        
        {requirement_summary}
        
        Rules:
        1. Start directly with '---'. 
        2. No commentary, no text markdown fences, no explanations. 
        3. Write clean native tasks matching the package types provided (e.g., use 'apt' module for System packages, 'pip' module for Python PIP packages, etc.).
        """

        payload = {
            "model": model_name,
            "prompt": prompt,
            "stream": True,
            "options": {
                "temperature": 0.0,
                "top_p": 0.1
            }
        }

        try:
            response = requests.post(ollama_url, json=payload, timeout=None, stream=True)
            if response.status_code != 200:
                return

            for line in response.iter_lines():
                if line:
                    chunk = json.loads(line.decode('utf-8'))
                    text = chunk.get("response", "")
                    if "```" in text:
                        text = text.replace("```yaml", "").replace("```", "")
                    print(text, end="", flush=True)
            print()
                        
        except Exception:
            pass

if __name__ == "__main__":
    #target_repo = "https://github.com/odissei-data/odissei-kg"
    target_repo = "https://github.com/sodascience/osmenrich"
    #target_repo = "https://github.com/odissei-data/ODISSEI-code-library"
    #target_repo = "https://github.com/rug-compling/alpino"
    #target_repo = "https://github.com/firmao/wimu"
    #target_repo = "https://github.com/dice-group/CEDAL"
    generate_fast_ansible(target_repo, model_name="llama3.2:1b")