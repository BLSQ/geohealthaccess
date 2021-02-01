from datetime import timedelta

from airflow import DAG
from airflow.models import Variable
from airflow.utils.dates import days_ago
from airflow.contrib.operators.kubernetes_pod_operator import KubernetesPodOperator

# Will be passed to all KubernetesPodOperator tasks
k8s_kwargs = {
    "image": "blsq/geohealthaccess:latest",
    "image_pull_policy": "Always",  # TODO: check if necessary
    "namespace": "default",
    "is_delete_operator_pod": True,
    "get_logs": True,
}
earthdata_env_variables = {
    "EARTHDATA_USERNAME": Variable.get("gha_earthdata_username"),
    "EARTHDATA_PASSWORD": Variable.get("gha_earthdata_password"),
}
cloud_storage_env_variables = {
    "AWS_ACCESS_KEY_ID": Variable.get("gha_aws_access_key_id"),
    "AWS_SECRET_ACCESS_KEY": Variable.get("gha_aws_secret_access_key"),
    "S3_REGION_NAME": Variable.get("gha_s3_region_name"),
    # "GOOGLE_APPLICATION_CREDENTIALS": Variable.get("gha_google_application_credentials"),
}

dag = DAG(
    "geohealthaccess",
    default_args={
        "owner": "Airflow",
        "depends_on_past": False,
        "start_date": days_ago(0),  # FIXME
        "catchup": False,  # FIXME
        "email": ["pvanliefland@bluesquarehub.com"],
        "email_on_failure": False,  # TODO: True
        "email_on_retry": False,  # TODO: True,
        "email_on_success": False,  # TODO: True,
        "retries": 0,  # FIXME
        "retry_delay": timedelta(minutes=5),
    },
    schedule_interval="0 3 1 * *",  # FIXME
    max_active_runs=10,
    concurrency=10,
)

download_image = KubernetesPodOperator(
    **k8s_kwargs,
    cmds=["echo"],
    arguments=['"Image downloaded!"',],
    task_id="gha_download_image",
    name="gha_download_image",
    dag=dag,
)

countries = ["SLE"]  # FIXME

for country in countries:
    # TODO: bucket configuration should be more flexible
    logs_dir = f"{Variable.get('gha_s3_bucket')}/{country}/logs"
    download_output_dir = f"{Variable.get('gha_s3_bucket')}/{country}/download"
    preprocess_output_dir = f"{Variable.get('gha_s3_bucket')}/{country}/preprocess"
    access_interm_dir = f"{Variable.get('gha_s3_bucket')}/{country}/interm"
    access_output_dir = f"{Variable.get('gha_s3_bucket')}/{country}/access"

    # step 1: download
    download_task_id = f"gha_download_{country.lower()}"
    download = KubernetesPodOperator(
        **k8s_kwargs,
        arguments=[
            "download",
            f"--country={country}",
            f"--output-dir={download_output_dir}",
            f"--logs-dir={logs_dir}",
        ],
        env_vars={**earthdata_env_variables, **cloud_storage_env_variables,},
        task_id=download_task_id,
        name=download_task_id,
        dag=dag,
    )

    # step 2: preprocess
    preprocess_task_id = f"gha_preprocess_{country.lower()}"
    preprocess = KubernetesPodOperator(
        **k8s_kwargs,
        arguments=[
            "preprocess",
            f"--country={country}",
            "--crs=EPSG:3857",  # TODO: check with Yann
            "--resolution=100",  # TODO: check with Yann
            f"--input-dir={download_output_dir}",
            f"--output-dir={preprocess_output_dir}",
        ],
        env_vars={**cloud_storage_env_variables,},
        task_id=preprocess_task_id,
        name=preprocess_task_id,
        dag=dag,
    )

    # step 3: access
    access_task_id = f"gha_access_{country.lower()}"
    access = KubernetesPodOperator(
        **k8s_kwargs,
        arguments=[
            "access",
            "--car",  # TODO: should be configurable
            f"--input-dir={preprocess_output_dir}",
            f"--interm-dir={access_interm_dir}",
            f"--output-dir={access_output_dir}",
        ],
        env_vars={**cloud_storage_env_variables,},
        task_id=access_task_id,
        name=access_task_id,
        dag=dag,
    )

    # define dependencies
    download_image >> download >> preprocess >> access
