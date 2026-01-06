# orca-slurm-batch-submit
A set of Python &amp; Bash scripts for creating and running SLURM runs in sub-folders for ORCA (or other code) inputs.

Requires python3

Can be used for creation of sub-folders containing the same ORCA inputs and slurm batch file. Running those scripts, with the '-d singleton' dependency is then performed using the bash script 'submit-singleton-sh'

Usage:

Step 1 - Create your preferred orca6.inp and slurm-batch-script inputs. Test initially to see if they submit with the correct CPU and memory requirements

Step 2 - Create your sub-folders on your local computer (or supercomputer) using eithe 'orca6-batch-create.py' or 'orca6-batch-prune-create.py'

Step 3 - Transfer those folders to your local supercomputer

Step 4 - test the submission using './submit-singleton.sh --dry-run'

Step 5 - If the submission runs without error you can submit, up to your defined limit, using './submit-singleton.sh'
