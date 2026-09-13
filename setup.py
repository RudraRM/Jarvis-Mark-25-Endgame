"""Configure JARVIS locally without putting credentials in command history."""
import argparse
import getpass
import json
import os
from pathlib import Path
import shutil
import sys

ROOT=Path(__file__).resolve().parent

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--hermes-path',type=Path)
    parser.add_argument('--hosted-asr',action='store_true')
    parser.add_argument('--install-skill',action='store_true')
    args=parser.parse_args()
    env=ROOT/'.env'
    if env.exists():
        parser.error('.env already exists; edit it locally to preserve existing settings')
    key=getpass.getpass('NVIDIA API key (hidden): ').strip()
    if not key:
        parser.error('A NVIDIA API key is required for the configured language model')
    values={'NVIDIA_API_KEY':key}
    if args.hermes_path:
        path=args.hermes_path.expanduser().resolve()
        if not (path/'run_agent.py').is_file():
            parser.error('Hermes checkout must contain run_agent.py')
        values['HERMES_AGENT_PATH']=str(path)
    if args.hosted_asr:
        values.update(RIVA_SERVER='grpc.nvcf.nvidia.com:443',RIVA_USE_SSL='1',
                      RIVA_FUNCTION_ID='71203149-d3b7-4460-8231-1be2543a1fca')
    template=(ROOT/'.env.example').read_text()
    lines=[]
    for line in template.splitlines():
        name=line.split('=',1)[0]
        if name in values:
            line=name+'='+json.dumps(values[name])
        lines.append(line)
    fd=os.open(env,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    with os.fdopen(fd,'w') as file:
        file.write('\n'.join(lines)+'\n')
    if args.install_skill:
        if not args.hermes_path:
            parser.error('--install-skill requires --hermes-path')
        home=Path(os.getenv('HERMES_HOME',str(Path.home()/'.hermes')))
        target=home/'skills/jarvis'
        if target.exists():
            print('Existing JARVIS skill preserved at '+str(target))
        else:
            shutil.copytree(ROOT/'skills/jarvis',target)
            print('Hermes skill installed at '+str(target))
    print('Configuration saved. Start with: '+sys.executable+' backend.py')

if __name__=='__main__':
    main()
