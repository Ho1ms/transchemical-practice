import re
import requests
from threading import Thread
from datetime import datetime

import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv, find_dotenv

load_dotenv(find_dotenv('.env'))

ERRORS = []
RESTART_URLS = []

db = psycopg2.connect(
    user=os.getenv('DB_USERNAME'),
    password=os.getenv("PASSWORD"),
    host=os.getenv('HOST'),
    database=os.getenv("DB_NAME")
)
cursor = db.cursor(cursor_factory=RealDictCursor)


def get_details_price(details: dict, manufacturer_id, category_id, brand_id):
    for detail in details['items']:
        for item in detail['spareParts']:

            pattern = "[.\/\\ ]"
            detail_price_ = requests.get(
                f'https://webapi.autodoc.ru/api/manufacturer/{manufacturer_id}/sparepart/{re.sub(pattern, "", item["partNumber"])}',
                timeout=(15, 15)
            )

            try:
                detail_price = detail_price_.json()
            except requests.exceptions.JSONDecodeError:
                print(f'ERROR: {detail_price_.url} {detail_price_} {item}')
                continue

            data = {
                'serial_number': detail_price['partNumber'],
                'name': detail_price.get('partName', item['name']),
                'description': detail_price.get('description', item['name']),
                'price': detail_price.get('minimalPrice', 0),
                'model_id': brand_id,
                'category_id': category_id
            }

            keys = ['serial_number', 'name', 'description', 'price', 'model_id', 'category_id']
            cursor.execute(f"INSERT INTO details ({', '.join(keys)}) VALUES (%s,%s,%s,%s,%s,%s) ON CONFLICT (model_id, serial_number) DO UPDATE SET price = %s, actual_in = %s",
                           [*(data[key] for key in keys), data['price'], datetime.now().strftime('%Y-%m-%d %H:%M:%S')])
            db.commit()

def get_model_info(res, catalog, manufacturer_id, brand_id):
    ssd = list(filter(lambda x: x['key'] == 'Ssd', res))[0]['value']
    car_id = list(filter(lambda x: x['key'] == 'CarID', res))[0]['value']

    details_type = requests.get(
        f'https://catalogoriginal.autodoc.ru/api/catalogs/original/brands/{catalog}/cars/{car_id}/quickgroups?ssd={ssd}').json()

    threads = []
    for category_detail in details_type['data']:
        for category_type in category_detail['children']:
            for detail_with_group in category_type['children']:
                print(category_type['name'], detail_with_group['name'])

                cursor.execute("INSERT INTO detail_categories (name) VALUES (%s) ON CONFLICT (name) DO UPDATE SET name = %s RETURNING id",
                               (detail_with_group['name'],detail_with_group['name']))
                db.commit()
                category_id = cursor.fetchone()['id']

                details = requests.post(
                    f'https://catalogoriginal.autodoc.ru/api/catalogs/original/brands/{catalog}/cars/{car_id}/quickgroups/{detail_with_group["quickGroupId"]}/units',
                    json={'Ssd': ssd}).json()
                get_details_price(details, manufacturer_id, category_id, brand_id)
                


def is_valid_model(res, r):
    all_actual = list(filter(lambda x: x['key'] == 'Actual', res['commonAttributes']))
    if len(all_actual) > 0:
        actual = all_actual[0]['value']
    else:
        actual = list(filter(lambda x: x['key'] == 'Actual', r['attributes']))[0]['value']

    if actual == '':
        return False

    actual_in = int(re.findall('\d{4}', actual)[0])
    if actual_in < 2005:
        return False
    return True


def get_model(brand):
    print('START', brand["name"])
    res = requests.get(
        f'https://catalogoriginal.autodoc.ru/api/catalogs/original/brands/{brand["code"]}/wizzard/0/modifications?ssd=$'
    ).json()

    catalog = list(filter(lambda x: x['key'] == 'Catalog', res['commonAttributes']))[0]['value']
    manufacturer_id = list(filter(lambda x: x['key'] == 'ManufacturerId', res['commonAttributes']))[0]['value']
    print(res)
    if len(list(filter(lambda x: x['key'] == 'Ssd', res['commonAttributes']))) == 0:
        for r in res['specificAttributes']:
            if not is_valid_model(res, r):
                continue
            get_model_info(r['attributes'], catalog, manufacturer_id, brand['id'])
    else:
        get_model_info(res['commonAttributes'], catalog, manufacturer_id, brand['id'])
    print('END', brand["name"])


def main():
    cursor.execute("SELECT id, name, code FROM brands")
    brands = cursor.fetchall()[3:]
    for brand in brands:
        get_model(brand)


if __name__ == '__main__':
    main()
    print(len(ERRORS), ERRORS)
