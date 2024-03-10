echo "BUILD START"
pythonpython3.11.4 -m pip install -r requirements.txt
python3.11.4 manage.py collectstatic --noinput --clear
echo "BUILD END"