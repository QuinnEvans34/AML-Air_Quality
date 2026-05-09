FROM astrocrpublic.azurecr.io/runtime:3.2-3

# /usr/local/airflow is the project root inside the container. Tasks import
# pipeline modules as `include.src.<module>`, so we need the parent of
# include/ on PYTHONPATH, not include/ itself.
ENV PYTHONPATH="/usr/local/airflow:${PYTHONPATH}"
