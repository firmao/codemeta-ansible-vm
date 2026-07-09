import os
import tempfile
import json
import requests
from git import Repo

def generate_fast_ansible(repo_url: str, model_name: str = "llama3.2:1b"):
    """
    Extracts minimal dependency signatures and generates an Ansible playbook fast.
    """
    ollama_url = "http://127.0.0.1:11434/api/generate"
    
    try:
        requests.get("http://127.0.0.1:11434", timeout=3)
    except requests.exceptions.ConnectionError:
        print("Error: Local Ollama service is not running.")
        return

    with tempfile.TemporaryDirectory() as tmp_dir:
        print(f"Cloning {repo_url}...")
        try:
            Repo.clone_from(repo_url, tmp_dir, depth=1)
        except Exception as e:
            print(f"Failed to clone: {e}")
            return

        #target_files = ["DESCRIPTION", "requirements.txt", "package.json", "docker-compose.yml", "codemeta.json", "environment.yml", "Pipfile", "pyproject.toml", "readme.md", "setup.py", "setup.cfg", "Makefile", "config.yaml", "config.yml"]
        target_files = ["requirements.txt", "codemeta.json", "readme.md"]
        extracted_lines = []
        
        # Aggressively extract only relevant configuration lines to minimize input tokens
        for root, _, files in os.walk(tmp_dir):
            for file in files:
                if file in target_files:
                    file_path = os.path.join(root, file)
                    try:
                        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                            # Only keep lines likely containing packages or system tools
                            lines = [line.strip() for line in f if len(line.strip()) > 2]
                            extracted_lines.append(f"--- File: {file} ---\n" + "\n".join(lines[:100]))
                    except Exception:
                        pass

        if not extracted_lines:
            # Fallback to a bare-minimum check if specific files aren't found
            extracted_lines.append("Repository analysis indicates a standard environment setup.")

        repo_context = "\n".join(extracted_lines)

        # Ultra-tight instructions to prevent conversational lag
        prompt = f"""
        Analyze these dependency configuration snippets:
        {repo_context}
        
        Generate ONLY a concise and compact Ubuntu-compatible Ansible Playbook YAML with the required software to reproduce the environment. 
        Start immediately with '---'.
        Do not include 'Install required packages'.
        Do not repeat anything under 'apt:
        name:'.
        The playbook should be optimized for speed and minimalism, focusing solely on essential packages and dependencies.
        """

        print(f"Generating optimized Ansible script via {model_name}...")
        
        payload = {
            "model": model_name,
            "prompt": prompt,
            "stream": True,
            "options": {
                "temperature": 0.1
            }
        }

        try:
            response = requests.post(ollama_url, json=payload, timeout=None, stream=True)
            print("\n" + "="*50 + "\n GENERATED ANSIBLE PLAYBOOK \n" + "="*50 + "\n")
            
            for line in response.iter_lines():
                if line:
                    chunk = json.loads(line.decode('utf-8'))
                    print(chunk.get("response", ""), end="", flush=True)
            print("\n")
            
        except Exception as e:
            print(f"Error communicating with local LLM engine: {e}")

if __name__ == "__main__":
    #target_repo = "https://github.com/sodascience/osmenrich"
    target_repo = "https://github.com/odissei-data/ODISSEI-code-library"
    generate_fast_ansible(target_repo, model_name="llama3.2:1b")