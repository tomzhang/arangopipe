#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Fri Jul 12 07:25:18 2019

@author: admin2
"""

from arangopipe.arangopipe_storage.arangopipe_api import ArangoPipe
from arangopipe.arangopipe_storage.arangopipe_admin_api import ArangoPipeAdmin
from arangopipe.arangopipe_storage.arangopipe_config import ArangoPipeConfig
import pandas as pd
import datetime as dt
import os
from sklearn.model_selection import train_test_split
from sklearn import linear_model
from sklearn.metrics import mean_squared_error, mean_absolute_error, r2_score
import uuid
import numpy as np
import logging
from arangopipe.arangopipe_storage.managed_service_conn_parameters import ManagedServiceConnParam
from arango import ArangoClient, DatabaseListError
from arangopipe.arangopipe_storage.custom_http_client import CustomHTTPClient

NUM_PERIODS = 22
go_back_days = dt.timedelta(days=30)
period_begin = dt.date.today()
period_end = period_begin - go_back_days
file_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                         "cal_housing.csv")
data = pd.read_csv(file_path)
preds = data.columns.tolist()
preds.remove("medianHouseValue")
X = data[preds]
Y = data["medianHouseValue"]
Y = np.log(Y)

# create logger with 'spam_application'
logger = logging.getLogger('arangopipe_test_data(models)_logger')
logger.setLevel(logging.DEBUG)
# create file handler which logs even debug messages
fh = logging.FileHandler('arangopipe_test_data(models).log')
fh.setLevel(logging.DEBUG)
# create console handler with a higher log level
ch = logging.StreamHandler()
ch.setLevel(logging.ERROR)
# create formatter and add it to the handlers
formatter = logging.Formatter(
    '%(asctime)s - %(name)s - %(levelname)s - %(message)s')
fh.setFormatter(formatter)
ch.setFormatter(formatter)
# add the handlers to the logger
logger.addHandler(fh)
logger.addHandler(ch)


def period_string_generator():
    global period_begin, period_end

    for period in range(NUM_PERIODS):
        period_str = str(period_begin) + " to " + str(period_end)
        period_begin = period_end - dt.timedelta(days=1)
        period_end = period_begin - go_back_days
        yield period_str


def dataset_generator():

    for period in range(NUM_PERIODS):
        X_train, X_test, y_train, y_test = train_test_split(X,
                                                            Y,
                                                            test_size=0.2)
        X_train, X_val, y_train, y_val = train_test_split(X_train,
                                                          y_train,
                                                          test_size=0.2)
        yield (X_train, X_test, y_train, y_test, X_val, y_val)


def eval_metrics(actual, pred):
    rmse = np.sqrt(mean_squared_error(actual, pred))
    mae = mean_absolute_error(actual, pred)
    r2 = r2_score(actual, pred)

    return rmse, mae, r2


def delete_users():
    print("Deleting users before test !")
    pl = ['_system', 'root', 'rajiv', 'node2vec_db_admin', 'susr']
    host_connection = "https://d874fc3f1fa5.arangodb.cloud:8529"
    client = ArangoClient(hosts= host_connection,\
                        http_client=CustomHTTPClient())
    sys_db = client.db('_system',\
                       username="root",\
                       password="KzcHiaZMPcQWw3aaNdXt")
    ul = sys_db.users()
    unl = [tu['username'] for tu in ul]
    for u in unl:
        if not u in pl:
            sys_db.delete_user(u)

    return


def delete_arangopipe_db():
    print("Deleting users before test !")

    host_connection = "https://d874fc3f1fa5.arangodb.cloud:8529"
    client = ArangoClient(hosts= host_connection,\
                        http_client=CustomHTTPClient())
    sys_db = client.db('_system',\
                       username="root",\
                       password="KzcHiaZMPcQWw3aaNdXt")
    try:
        if sys_db.has_database("arangopipe"):
            print(
                "Before starting the test, cleaning up arangopipe instances..."
            )
            sys_db.delete_database("arangopipe")
        else:
            print("Test Prep: The database arangopipe does not exist !")

    except DatabaseListError as err:
        print.error(err)
        print("Error code: " + str(err.error_code) + " received !")
        print("Error Message: " + str(err.error_message))

    return


def generate_runs(clean=False):
    delete_users()
    delete_arangopipe_db()
    conn_config = ArangoPipeConfig()
    mscp = ManagedServiceConnParam()
    conn_params = { mscp.DB_SERVICE_HOST : "d874fc3f1fa5.arangodb.cloud", \
                    mscp.DB_USER_NAME : "arangopipe",\
                    mscp.DB_PASSWORD : "arangopipe",\
                    mscp.DB_NAME : "arangopipe", \
                    mscp.DB_ROOT_USER : "root",\
                    mscp.DB_ROOT_USER_PASSWORD : "open sesame",\
                    mscp.DB_SERVICE_END_POINT : "apmdb",\
                    mscp.DB_SERVICE_NAME : "createDB",\
                    mscp.DB_SERVICE_PORT : 8529,\
                    mscp.DB_CONN_PROTOCOL : 'https'}

    conn_config = conn_config.create_connection_config(conn_params)
    admin = ArangoPipeAdmin(reuse_connection=False, config=conn_config)
    ap_config = admin.get_config()
    ap = ArangoPipe(config=ap_config)

    if clean:
        admin.delete_arangomldb()
        admin.create_db()
        admin.create_enterprise_ml_graph()

    proj_info = {"name": "Home_Value_Assessor"}
    proj_reg = admin.register_project(proj_info)

    period = period_string_generator()
    ds_info = {"description": "Housing Price Data"}
    featureset = data.dtypes.to_dict()
    featureset = {k: str(featureset[k]) for k in featureset}
    count = 1

    for data_tuple in dataset_generator():
        logger.info("Processing Dataset:" + str(count))
        count = count + 1
        aperiod = next(period)
        X_train = data_tuple[0]
        X_test = data_tuple[1]
        y_train = data_tuple[2]
        y_test = data_tuple[3]
        X_val = data_tuple[4]
        y_val = data_tuple[5]
        alpha_random = np.random.uniform(0.0005, 0.001)
        lrm = linear_model.Lasso(alpha=alpha_random)
        lrm.fit(X_train, y_train)
        predicted_val = lrm.predict(X_val)
        (rmse, mae, r2) = eval_metrics(y_val, predicted_val)
        ruuid = uuid.uuid4()
        model_perf = {"rmse": rmse, "r2": r2, "mae": mae, "run_id": str(ruuid), \
                      "timestamp": str(dt.datetime.now())}
        serving_pred = lrm.predict(X_test)
        (rmse, mae, r2) = eval_metrics(y_test, serving_pred)
        ex_servingperf = {"rmse": rmse, "r2": r2, "mae": mae,\
                      "period" : aperiod}
        deployment_tag = "Deployment_HPE_" + aperiod
        dataset_tag = "Housing_Dataset_" + aperiod
        pipeline_tag = "Pipeline_HPE" + aperiod
        feature_pipeline_tag = "Feature Pipeline HPE" + aperiod
        ds_info["name"] = dataset_tag
        ds_info["tag"] = dataset_tag
        ds_info["source"] = "Housing Price Operational Data Store"
        featureset["generated_by"] = feature_pipeline_tag
        featureset["name"] = "log_transformed_house_value"
        featureset["tag"] = dataset_tag

        ds_reg = ap.register_dataset(ds_info)
        fs_reg = ap.register_featureset(featureset, ds_reg["_key"])
        model_tag = "model_period:" + aperiod
        model_info = {"name": "Housing Regression Model",\
                      "type": "LASSO regression", "tag": model_tag}
        model_reg = ap.register_model(model_info,
                                      project="Home_Value_Assessor")
        model_params = {"alpha": alpha_random, "run_id": str(ruuid)}
        run_info = {"dataset" : ds_reg["_key"],\
                    "featureset": fs_reg["_key"],\
                    "run_id": str(ruuid),\
                    "model": model_reg["_key"],\
                    "model-params": model_params,\
                    "model-perf": model_perf,\
                    "pipeline" : pipeline_tag,\
                    "project": "Housing Price Assessor",
                    "tag_for_deployment": True,\
                    "deployment_tag": deployment_tag}
        ap.log_run(run_info)
        admin.register_deployment(deployment_tag)
        user_id = "Arangopipe Test Data Generator"
        ap.log_serving_perf(ex_servingperf, deployment_tag, user_id)

    return
