# gdrive-lambda
gdrive integration with lambda

The purpose of this project for the time being is to pass json data to a csv
file for end users who use Gdrive across the organization. 

This project is currently in beta status. Issues and PRs welcome!

#### Example usage in jupyter notebook with pandas

```python
# Set GDRIVE_TEST_URL and GDRIVE_TEST_KEY in your enviornment vars.
from pandas_ext.gdrive import read_gdrive, to_gdrive
results = read_gdrive('https://drive.google.com/uc?id=ABCDEFG')
wresults = to_gdrive('atest.csv', results.df, results.folder_id)                             
wresults
'https://drive.google.com/uc?id=ABCXYZ&export=download'
```

#### Pre-Requisites
* pyenv # for saving this project as a 2.7 project for aws lambda
* AWS Credentials configured 
* Gdrive API enabled
* creds.p12 for google drive service account


#### Installation

```bash
git clone git@github.com:richiverse/gdrive-lambda.git && cd gdrive-lambda
pyenv local 2.7.12
virtualenv venv
. ./venv/bin/activate
pip install -r requirements.txt
zappa init
zappa deploy dev
```

#### Setup in Google Drive
1. Create a folder somewhere in Gdrive where you would like to save report sub-folders and take note of it's ID.
Set this ID so the GDRIVE_PARENT_FOLDER_ID in your environment variables. This can be overridden in the POST as well.
2. Run the service at least once. # See testing below
3. Share the folders with specific people you want to send the report to.
4. In order to make this more useful, you will have to dynamically generate the json and save it periodically.
For this I will use another set of lambdas so stay tuned!

#### To test locally

Personally, I use httpie to test but cURL should work just as well.

In the first terminal window, run the following
```bash
python app.py
```

In another terminal window:
```bash
http POST http://localhost:5000/gdrive < post_params.json
```

or:
```bash
http POST http://localhost:5000/gdrive file_name=test.csv data:=@post_params2.json
```

#### TODO

[ ] Work with file types other than CSV (Ideally using odo)

[ ] Work with Native Google Spreadsheet
