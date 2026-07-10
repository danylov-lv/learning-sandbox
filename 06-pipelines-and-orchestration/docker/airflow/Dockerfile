FROM apache/airflow:3.1.0

USER root
RUN apt-get update \
    && apt-get install -y --no-install-recommends openjdk-17-jre-headless \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*
ENV JAVA_HOME=/usr/lib/jvm/java-17-openjdk-amd64
ENV PATH="${JAVA_HOME}/bin:${PATH}"

USER airflow
RUN pip install --no-cache-dir \
    pyspark==3.5.* \
    pandera \
    "psycopg[binary]" \
    requests

# hadoop-aws 3.3.4 is the version bundled with pyspark 3.5.x's Hadoop client libs;
# aws-java-sdk-bundle 1.12.262 is the exact AWS SDK build hadoop-aws:3.3.4 was compiled against.
# Pre-fetching both into pyspark's jars/ dir gives s3a:// support with no network access at spark-submit time.
RUN PYSPARK_JARS_DIR="$(python -c "import pyspark, os; print(os.path.join(os.path.dirname(pyspark.__file__), 'jars'))")" \
    && curl -fsSL -o "${PYSPARK_JARS_DIR}/hadoop-aws-3.3.4.jar" \
         https://repo1.maven.org/maven2/org/apache/hadoop/hadoop-aws/3.3.4/hadoop-aws-3.3.4.jar \
    && curl -fsSL -o "${PYSPARK_JARS_DIR}/aws-java-sdk-bundle-1.12.262.jar" \
         https://repo1.maven.org/maven2/com/amazonaws/aws-java-sdk-bundle/1.12.262/aws-java-sdk-bundle-1.12.262.jar
