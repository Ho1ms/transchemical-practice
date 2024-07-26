import json
import io, os
import xlwt
import psycopg2
from psycopg2.extras import RealDictCursor
from flask import Flask, request, render_template, make_response, send_file
from datetime import datetime, timedelta
import pandas as pd
from json import dumps
from flask_cors import cross_origin, CORS
from dotenv import load_dotenv, find_dotenv

load_dotenv(find_dotenv('.env'))

app = Flask('TRANSCHEMICAL')
CORS(app)

db = psycopg2.connect(
    user=os.getenv('DB_USERNAME'),
    password=os.getenv("PASSWORD"),
    host=os.getenv('HOST'),
    database=os.getenv("DB_NAME")
)
cursor = db.cursor(cursor_factory=RealDictCursor)
PAGES = [{'path': 'index', 'title': 'Список деталей', 'icon': 'database-fill-gear'},
         {'path': 'scud_handler', 'title': 'Учёт рабочего времени', 'icon': "calendar3"}]
LIMITS = [50, 100, 250, 500]


def add_row(ws, index, row):
    ws.write(index, 0, row['serial_number'])
    ws.write(index, 1, row['model_name'])
    ws.write(index, 2, row['category_name'])
    ws.write(index, 3, row['name'])
    ws.write(index, 4, row['description'])
    ws.write(index, 5, row['price'])
    ws.write(index, 6, row['actual_in'].strftime('%d.%m.%Y'))


def make_query(filter_data):
    args = {}
    if filter_data['query_text'] != '':
        args['text'] = '%' + filter_data['query_text'] + '%'
    if 'all' not in filter_data['brands']:
        args['brands'] = list(map(int, filter_data['brands']))
    if '-1' != filter_data['limit']:
        args['limit'] = int(filter_data['limit'])
    queries = {
        'text': "CONCAT(dc.name, d.name, d.description) LIKE %s",
        'brands': 'b.id = ANY(%s)'
    }

    query_string = [queries[i] for i in args.keys() if i in ('text', 'brands')]
    sql_query = f""" SELECT d.*, b.name model_name, dc.name category_name
            	    FROM details d
            	    INNER JOIN brands b ON b.id = d.model_id
            	    INNER JOIN detail_categories dc ON dc.id = d.category_id
            	    {"WHERE" if len(query_string) > 0 else ''} {" AND ".join(query_string)}
            	    ORDER BY price {"DESC" if filter_data["order_by_price"] else ""}, actual_in {"DESC" if filter_data["order_by_new"] else ""}
            	    {"LIMIT %s" if 'limit' in args else ""}
            	"""
    return sql_query, list(args.values())


@app.get('/')
def index():
    cursor.execute("""SELECT id, name FROM brands""")
    brands = cursor.fetchall()

    default_filter = {
        'order_by_price': False,
        'order_by_new': False,
        'query_text': '',
        'brands': ['all'],
        'limit': 100
    }
    filter_data = request.cookies.get('filter')
    if filter_data is None:
        filter_data = default_filter
    else:
        filter_data = json.loads(filter_data)
    cursor.execute(*make_query(filter_data))

    rows = cursor.fetchall()
    return render_template('index.html', rows=rows,
                           pages=PAGES,
                           brands=brands, filter=filter_data, str=str, limits=LIMITS)


@app.post('/')
def index_form_handler():
    data = request.form

    if data is None:
        return 'Missing data', 401

    order_by_price = data.get('order_by_price', False)
    order_by_new = data.get('order_by_new', False)
    brands = data.getlist('brands')
    limit = data.get('limit', 100)
    is_export = data.get('export')
    filter_data = {
        'order_by_price': order_by_price,
        'order_by_new': order_by_new,
        'query_text': data.get('text'),
        'brands': brands,
        'limit': limit
    }

    cursor.execute("""SELECT id, name FROM brands""")
    brands_list = cursor.fetchall()

    cursor.execute(*make_query(filter_data))

    rows = cursor.fetchall()

    if is_export is not None:
        wb = xlwt.Workbook()
        ws = wb.add_sheet('Data')
        ws.write(0, 0, 'Номер детали')
        ws.write(0, 1, 'Производитель')
        ws.write(0, 2, 'Деталь')
        ws.write(0, 3, 'Элемент')
        ws.write(0, 4, 'Описание')
        ws.write(0, 5, 'Цена')
        ws.write(0, 6, 'Актуально на')
        for i, row in enumerate(rows, start=1):
            add_row(ws, i, row)
        name = f'report_{datetime.now().timestamp()}.xls'
        wb.save(name)
        return_data = io.BytesIO()
        with open(name, 'rb') as fo:
            return_data.write(fo.read())
        return_data.seek(0)
        os.remove(name)

        return send_file(return_data, as_attachment=True, download_name=f'Запчасти_{datetime.now()}.xls')

    res = make_response(render_template('index.html', rows=rows,
                                        pages=PAGES,
                                        brands=brands_list, filter=filter_data, str=str, limits=LIMITS))
    res.set_cookie('filter', json.dumps(filter_data), max_age=365 * 24 * 3600)
    return res


def str_to_date(date_string):
    return datetime.strptime(date_string, "%Y-%m-%d %H:%M:%S")


def make_tasks(df, users_row_list, init_date, end_date):
    user_list = {}
    users_names_list = []
    for user in users_row_list:
        user_list[user['id']] = (user['row_id'], user['name'])
        users_names_list.append(user['name'])

    users = {}

    for i, log in enumerate(df.to_dict(orient="records")):
        user_id = log['user_id']
        users.setdefault(user_id, [{}])
        target = users[user_id][-1]
        log_info = {
            'id': i,
            'row_index': user_list[log['user_id']][0],
            'name': user_list[log['user_id']][1],
            'progress': 100
        }
        log['date'] = log['date'].strftime("%Y-%m-%d %H:%M:%S")
        if log['type'] == 'IN':
            if 'end' in target:
                users[user_id].append({"start": log['date'], **log_info})
                continue
            if 'start' in target:
                if abs(str_to_date(log['date']) - str_to_date(target['start'])) < timedelta(seconds=300):
                    users[user_id][-1]['start'] = log['date']
                elif abs(str_to_date(log['date']) - str_to_date(target['start'])) > timedelta(hours=7):
                    users[user_id][-1]['end'] = (str_to_date(target['start']) + timedelta(hours=7)).strftime(
                        "%Y-%m-%d %H:%M:%S")
                    users[user_id].append({"start": log['date'], **log_info})
                    continue
                elif abs(str_to_date(end_date) - str_to_date(target['start'])) < timedelta(hours=7):
                    users[user_id][-1]['start'] = end_date

            users[user_id][-1] = {**log_info, 'start': log['date']}
        elif log['type'] == 'OUT':
            if 'start' not in target:
                if abs(str_to_date(log['date']) - str_to_date(init_date)) > timedelta(hours=7):
                    users[user_id][-1] = {"start": (str_to_date(log['date']) - timedelta(hours=7)).strftime("%Y-%m-%d %H:%M:%S"), 'end': log['date'], **log_info}

                else:
                    users[user_id][-1] = {"start": init_date, 'end': log['date'], **log_info}
                continue
            if 'start' in target:
                if abs(str_to_date(log['date']) - str_to_date(target['start'])) > timedelta(hours=17):
                    users[user_id][-1]['end'] = (str_to_date(target['start']) + timedelta(hours=7)).strftime("%Y-%m-%d %H:%M:%S")
                    users[user_id].append({"start": (str_to_date(log['date']) - timedelta(hours=7)).strftime("%Y-%m-%d %H:%M:%S"), 'end': log['date'], **log_info})

            if 'end' in target:
                if abs(str_to_date(log['date']) - str_to_date(target['end'])) < timedelta(seconds=300):
                    users[user_id][-1]['end'] = log['date']
                elif abs(str_to_date(log['date']) - str_to_date(target['end'])) > timedelta(hours=7):
                    users[user_id].append({"start": (str_to_date(log['date']) - timedelta(hours=7)).strftime("%Y-%m-%d %H:%M:%S"), 'end': log['date'], **log_info})
                    continue
            users[user_id][-1]['end'] = log['date']

    data = []
    for i in users.values():
        data.extend(i)

    return data, users_names_list


@app.get('/scud')
@cross_origin()
def scud_handler():
    cursor.execute("""SELECT p1.id, p1.name FROM personal p1
	WHERE p1.type = 'DEP' AND (SELECT COUNT(id) FROM personal p2 WHERE p1.id = p2.parent_id AND p2.type='EMP') > 0""")
    depts = cursor.fetchall()

    return render_template('time_manager.html', pages=PAGES, depts=depts, url_api=os.getenv('HOST_API'))


@app.get('/scud/data')
@cross_origin()
def scud_data_handler():
    args = request.args
    init_date = (args.get('start') or datetime(year=2024, month=7, day=1).strftime("%Y-%m-%d")) + ' 00:00:00'
    end_date = (args.get('end') or datetime(year=2024, month=7, day=10).strftime("%Y-%m-%d")) + ' 00:00:00'
    dep_id = args.get('dep') or 'DEMO'
    if dep_id == 'DEMO' or not dep_id.isdigit():
        return dumps({'names': [], 'tasks': []}, ensure_ascii=False)

    cursor.execute("""SELECT  
     logs.logtime as date, users.id as user_id, direction as type
    FROM logs 
     LEFT JOIN personal as users ON users.id = logs.EMPHINT
    WHERE LOGTIME > %s AND logtime < %s AND logs.DEVHINT = 18 AND users.type = 'EMP' and users.status = 'AVAILABLE' AND users.parent_id = %s
    ORDER BY logs.id;
    """, (init_date, end_date, dep_id))

    rows = cursor.fetchall()
    cursor.execute("""SELECT (ROW_NUMBER() OVER (ORDER BY users.name)) -1 AS row_id, users.id, users.name
    FROM personal as users WHERE users.type = 'EMP' and users.status = 'AVAILABLE'  AND users.parent_id = %s ORDER BY users.name
    ;
    """, (dep_id,))
    users_row_list = cursor.fetchall()
    df = pd.DataFrame(rows)

    tasks, users_names_list = make_tasks(df, users_row_list, init_date, end_date)
    return dumps({'names': users_names_list, 'tasks': tasks}, ensure_ascii=False)


app.run(debug=True, port=8070)
