from collections import namedtuple, OrderedDict
from flask import Flask, g, render_template, request, session, url_for
from sqlalchemy import create_engine, MetaData
# from sqlalchemy.orm import sessionmaker
from sqlalchemy.sql import select, text
from config import AppConfig

app = Flask('uni-capacity-app')
app.secret_key = 'f8f0f791c2d1f02f3c2a7d8eaf5a45aecd6f7fe187f9b709'
# DB connection initialization
engine = create_engine(AppConfig.configs()['Database']['db_url'], echo=False)
meta = MetaData()
# Session = sessionmaker(bind=engine)
meta.reflect(bind=engine)


# DB function area
def connect_db():
    conn = engine.connect()
    return conn


def get_db_connection():
    if not hasattr(g, 'db_conn'):
        g.db_conn = connect_db()
    return g.db_conn


@app.teardown_appcontext
def close_db_connection(error):
    if hasattr(g, 'db_conn'):
        g.db_conn.close()


SitebarCat = namedtuple('sitebar_cat', 'name items')
SitebarItem = namedtuple('sitebar_item', 'name func_name enabled')

inputs = SitebarCat('Input', [
    SitebarItem('Product Priority', 'get_itemgroup_priority', True),
    SitebarItem('Scheduled Downtime', 'get_downtime', True),
    # SitebarItem('Strategy', 'strategies', False),
    SitebarItem('Tool Parameter', 'get_tool_param', True),
    # SitebarItem('Tool Priority', 'tool-prio', True),
    SitebarItem('UPH', 'get_uph', True),
    SitebarItem('Working Hour', 'get_working_hour', True),
    SitebarItem('Yield', 'get_yield', True),
])
reports = SitebarCat('Report', [
    SitebarItem('Capacity Roll-up', 'get_capacity_roll_up', True),
    SitebarItem('Demand & Supported', 'get_demand_supported', True),
    SitebarItem('Limiter Chart', 'get_limiter_chart', True),
    SitebarItem('Run Rate', 'get_runrate', True),
    SitebarItem('Tool Required', 'get_tool_required', True),
])
solver = SitebarCat('Solver', [
    SitebarItem('Run Solve', 'get_solver_run', True),
    SitebarItem('Solver Parameters', 'get_solver_param', True)
])
version_management = SitebarCat('Version Management', [
    SitebarItem('Data Load', 'get_data_load', True),
    SitebarItem('Versions', 'get_versions', True),
])
sidebar_cats = (inputs, reports, solver, version_management)


def filter_version(table, version_id):
    return table.c.version_id == version_id


@app.route('/')
@app.route('/versions')
def get_versions():
    version_t = meta.tables['data_versions']
    query = select(
        [version_t.c.id, version_t.c.name, version_t.c.version_type,
         version_t.c.description, version_t.c.created_at,
         version_t.c.created_by]). \
        where(version_t.c.deleted == False). \
        order_by(version_t.c.id.desc())
    conn = get_db_connection()
    result = conn.execute(query)
    col_headers = ['Version ID', 'Version Name', 'Description', 'Version Type',
                   'Created At', 'Created By']
    cell_data = [[row['id'], row['name'], row['description'],
                  row['version_type'], str(row['created_at']),
                  row['created_by']] for row in result]
    return render_template('version.html', cats=sidebar_cats,
                           col_headers=col_headers, cell_data=cell_data)


def fetch_version_in_session(update=False):
    if update or 'versions' not in session:
        version_t = meta.tables['data_versions']
        query = select([version_t.c.id, version_t.c.name]). \
            where(version_t.c.deleted == False). \
            order_by(version_t.c.id.desc())
        conn = get_db_connection()
        result = conn.execute(query)
        row_dict = [dict(row) for row in result]
        session['versions'] = row_dict

    if 'version_id' not in session:
        session['version_id'] = session['versions'][0]['id']

    return session['versions'], session['version_id']


@app.route('/products/priorities', methods=['GET', 'POST'])
def get_itemgroup_priority():
    _versions, _version_id = fetch_version_in_session()
    conn = get_db_connection()

    ig_l_t = meta.tables['data_itemgroup_locs']
    ig_t = meta.tables['ref_itemgroups']
    loc_t = meta.tables['ref_locations']
    ig_l_j = ig_l_t.join(ig_t).join(loc_t)
    _itemgroup_locs = conn.execute(
        select([ig_t.c.id.label('ig_id'), ig_t.c.name.label('ig_name'),
                loc_t.c.id.label('l_id'), loc_t.c.name.label('l_name')]).
            select_from(ig_l_j).
            where(filter_version(ig_l_t, _version_id)))

    _itemgroups = {}
    _locs = {}
    for row in _itemgroup_locs:
        ig_id = row['ig_id']
        ig_name = row['ig_name']
        loc_id = row['l_id']
        l_name = row['l_name']
        if ig_id not in _itemgroups:
            _itemgroups[ig_id] = ig_name
        if l_name not in _locs:
            _locs[loc_id] = l_name

    bucket_t = meta.tables['ref_buckets']
    _buckets = conn.execute(select([bucket_t.c.name]))

    _priorities = OrderedDict()
    if request.method == 'POST':
        ver_id_sel = request.form.get('v')
        if ver_id_sel:
            session['version_id'] = ver_id_sel

        igs = request.form.getlist('ig')
        locs = request.form.getlist('l')

        iglp_t = meta.tables['data_itemgroup_locs_params']
        param_t = meta.tables['ref_parameter_types']
        iglp_j = iglp_t.join(ig_l_j). \
            join(param_t, param_t.c.id == iglp_t.c.parameter_type_id). \
            join(bucket_t, bucket_t.c.id == iglp_t.c.bucket_id)

        iglp_results = conn.execute(
            select([iglp_t.c.itemgroup_loc_id, iglp_t.c.parameter_type_id,
                    param_t.c.type_name.label('parameter_type_name'),
                    ig_t.c.name.label('ig_name'), loc_t.c.name.label('l_name'),
                    bucket_t.c.name.label('yyyymm'), iglp_t.c.value])
                .select_from(iglp_j)
                .where(filter_version(iglp_t, ver_id_sel) &
                       loc_t.c.id.in_(locs) & ig_t.c.id.in_(igs) &
                       (param_t.c.type_name == 'Priority'))
                .order_by(ig_t.c.id, loc_t.c.id,
                          bucket_t.c.id))

        for row in iglp_results:
            ig_name = row['ig_name']
            l_name = row['l_name']
            yyyymm = row['yyyymm']
            _value = row['value']

            if ig_name not in _priorities:
                _priorities[ig_name] = OrderedDict()
            if l_name not in _priorities[ig_name]:
                _priorities[ig_name][l_name] = OrderedDict()
            if yyyymm not in _priorities[ig_name][l_name]:
                _priorities[ig_name][l_name][yyyymm] = _value

    return render_template('itemgroup-priority.html', cats=sidebar_cats,
                           versions=_versions, locs=_locs, buckets=_buckets,
                           itemgroups=_itemgroups, priorities=_priorities)


@app.route('/tools/downtimes')
def get_downtime():
    pass


@app.route('/operations/downtimes')
def get_tool_param():
    pass


@app.route('/uphs')
def get_uph():
    pass


@app.route('/working-hour')
def get_working_hour():
    pass


@app.route('/processgroups/yields')
def get_yield():
    pass


@app.route('/capacity-roll-up')
def get_capacity_roll_up():
    pass


@app.route('/demand-supported')
def get_demand_supported():
    pass


@app.route('/limiter-chart')
def get_limiter_chart():
    pass


@app.route('/runrates')
def get_runrate():
    pass


@app.route('/tools/required')
def get_tool_required():
    _versions, _version_id = fetch_version_in_session()
    conn = get_db_connection()
    b_t = meta.tables['ref_buckets']
    _buckets = conn.execute(select([b_t.c.name]).order_by(b_t.c.name))

    col_headers = ['Product', 'Location', 'Area', 'Sub Process', 'Machine']
    col_headers.extend([row['name'] for row in _buckets])

    cell_data = []
    query = text(
        """
        SELECT digg.name AS Product, rl.name AS Location, rs.name AS Area,
          ro.name AS Process, rt.name AS Machine, rb.name AS YYYYMM,
          round(otrv.value, 2) AS Tool_Required
        FROM out_tool_required_values otrv
          JOIN data_processgroups dpg ON dpg.id = otrv.processgroup_id
                                         AND dpg.version_id = otrv.version_id
          JOIN data_itemgroupgroup_locs diggl ON diggl.id = dpg.itemgroupgroup_loc_id
                                                 AND diggl.version_id = otrv.version_id
          JOIN ref_itemgroupgroups digg ON digg.id = diggl.itemgroupgroup_id
          JOIN ref_operations ro ON ro.id = otrv.operation_id
          JOIN ref_stages rs ON rs.id = dpg.stage_id
          JOIN data_tool_locs dtl ON dtl.id = otrv.tool_loc_id
                                     AND dtl.version_id = otrv.version_id
          JOIN ref_tools rt ON rt.id = dtl.tool_id
          JOIN ref_locations rl ON rl.id = diggl.loc_id AND rl.id = dtl.loc_id
          JOIN ref_buckets rb ON rb.id = otrv.bucket_id
        WHERE otrv.version_id = 2 AND rl.id = 2
        ORDER BY rl.name, digg.name, ro.name, rt.name, rb.name;
        """)
    tool_req_ot = conn.execute(query)
    tool_req_dict = OrderedDict()
    for row in tool_req_ot:
        rt_cols = [row['Product'], row['Location'], row['Area'],
                   row['Process'], row['Machine']]
        routine = '_'.join(rt_cols)
        if routine not in tool_req_dict:
            tool_req_dict[routine] = rt_cols
        tool_req_dict[routine].append(row['Tool_Required'])

    return render_template('tool-required.html', cats=sidebar_cats,
                           versions=_versions, buckets=_buckets,
                           col_headers=col_headers,
                           cell_data=list(tool_req_dict.values()))


@app.route('/solver/run')
def get_solver_run():
    _versions, _version_id = fetch_version_in_session()

    return render_template('run-solve.html', cats=sidebar_cats,
                           versions=_versions)


@app.route('/solver/parameters')
def get_solver_param():
    pass


@app.route('/data-load')
def get_data_load():
    pass


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0')

    with app.test_request_context():
        print(url_for('itemgroup_priority'))
