import os

OUTPUT_FILE = "decretometro_codigo_completo.md"
EXCLUDE_DIRS = {'.git', '.venv', '__pycache__', '.agents', 'brain', 'scratch', '.pytest_cache'}
EXCLUDE_FILES = {'decretometro.db', OUTPUT_FILE}
ALLOWED_EXTENSIONS = {'.py', '.css', '.bat', '.sh', '.md', '.sql', '.toml'}

def export_codebase():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    output_path = os.path.join(base_dir, OUTPUT_FILE)
    
    written_count = 0
    with open(output_path, 'w', encoding='utf-8') as out:
        out.write("# Código Consolidado del Proyecto Decretómetro\n\n")
        out.write("Este archivo contiene la totalidad del código fuente y configuraciones del proyecto Decretómetro.\n\n")
        
        for root, dirs, files in os.walk(base_dir):
            # Filtrar carpetas excluidas
            dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS and not d.startswith('.')]
            
            for file in sorted(files):
                if file in EXCLUDE_FILES or file.endswith('.pyc') or file.endswith('.db'):
                    continue
                
                ext = os.path.splitext(file)[1]
                if ext in ALLOWED_EXTENSIONS or file in {'requirements.txt', 'AGENTS.md'}:
                    file_path = os.path.join(root, file)
                    rel_path = os.path.relpath(file_path, base_dir)
                    
                    out.write(f"## Archivo: `{rel_path}`\n\n")
                    
                    lang = ext.replace('.', '')
                    if lang == 'py':
                        lang = 'python'
                    elif lang == 'bat' or lang == 'cmd':
                        lang = 'cmd'
                    elif lang == '':
                        lang = 'text'
                    
                    out.write(f"```{lang}\n")
                    try:
                        with open(file_path, 'r', encoding='utf-8') as f:
                            out.write(f.read())
                    except Exception as e:
                        out.write(f"# Error al leer archivo: {e}\n")
                    out.write("\n```\n\n")
                    written_count += 1
                    
    print(f"Exportación finalizada con éxito. Archivos procesados: {written_count}")

if __name__ == "__main__":
    export_codebase()
