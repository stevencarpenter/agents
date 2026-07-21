"""Builds the churn model training set. Runs weekly before retraining."""

from pyspark.sql import DataFrame, SparkSession, functions as F

spark = SparkSession.builder.getOrCreate()


def build_training_set() -> DataFrame:
    # Labels: did the customer churn in the 30 days after the observation date?
    labels = spark.table("gold.churn_labels")  # customer_id, observation_date, churned

    # Features are recomputed fresh from the full history each run.
    orders = spark.table("silver.orders")
    features = (
        orders.groupBy("customer_id")
        .agg(
            F.count("*").alias("lifetime_order_count"),
            F.avg("order_value").alias("avg_order_value"),
            F.max("event_timestamp").alias("last_order_at"),
        )
    )

    return labels.join(features, on="customer_id", how="left")


def serving_feature_sql() -> str:
    # Kept in sync with the API repo's copy by convention.
    return """
        SELECT customer_id, COUNT(*) AS lifetime_order_count,
               AVG(order_value) AS avg_order_value, MAX(event_timestamp) AS last_order_at
        FROM silver.orders GROUP BY customer_id
    """


def build_support_ticket_embeddings() -> DataFrame:
    # Embed the latest ticket text for each customer for the RAG explainer.
    tickets = spark.table("silver.support_tickets")
    latest = tickets.groupBy("customer_id").agg(F.max_by("body", "created_at").alias("body"))
    return latest.withColumn("embedding", F.expr("ai_embed(body)"))


if __name__ == "__main__":
    build_training_set().write.mode("overwrite").saveAsTable("gold.churn_training")
    build_support_ticket_embeddings().write.mode("overwrite").saveAsTable("gold.ticket_embeddings")
