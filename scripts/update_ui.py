import re

def process_file(filename):
    with open(filename, 'r', encoding='utf-8') as f:
        content = f.read()

    # We need to find forms and replace them with containers, and move op inputs
    # But it's easier to just do targeted regex replaces for the OP fields.
    pass

if __name__ == '__main__':
    process_file('components/tab_estado.py')
    process_file('components/tab_distribuir.py')
