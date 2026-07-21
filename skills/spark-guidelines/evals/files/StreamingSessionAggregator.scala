// Problematic streaming job — driver OOM after ~6 hours
package com.example.sessions

import org.apache.spark.sql.{Dataset, SparkSession}
import org.apache.spark.sql.streaming.{GroupState, GroupStateTimeout, OutputMode}
import org.apache.spark.sql.functions._
import org.apache.spark.sql.types._

case class PageView(sessionId: String, userId: String, page: String, eventTime: java.sql.Timestamp)
case class SessionMetrics(sessionId: String, pageCount: Int, uniquePages: Seq[String])

object StreamingSessionAggregator {
  def main(args: Array[String]): Unit = {
    val spark = SparkSession.builder().appName("session-agg").getOrCreate()
    import spark.implicits._

    val schema = new StructType()
      .add("sessionId", StringType)
      .add("userId", StringType)
      .add("page", StringType)
      .add("eventTime", TimestampType)

    val views = spark.readStream
      .format("kafka")
      .option("subscribe", "page-views")
      .load()
      .select(from_json(col("value").cast("string"), schema).as("data"))
      .select("data.*")
      .as[PageView]
    // NOTE: no watermark defined — processing all events as they arrive

    val sessionMetrics = views
      .groupByKey(_.sessionId)
      .flatMapGroupsWithState[Map[String, Int], SessionMetrics](
        OutputMode.Update(),
        GroupStateTimeout.NoTimeout()  // state never expires
      ) { (sessionId, events, state) =>
        val pageCounts = state.getOption.getOrElse(Map.empty)
        var updated = pageCounts
        events.foreach { e =>
          updated = updated + (e.page -> (updated.getOrElse(e.page, 0) + 1))
        }
        state.update(updated)

        val uniquePages = updated.keys.toSeq
        Iterator(SessionMetrics(sessionId, updated.values.sum, uniquePages))
      }

    sessionMetrics.writeStream
      .format("console")
      .outputMode("update")
      .start()
      .awaitTermination()
  }
}
