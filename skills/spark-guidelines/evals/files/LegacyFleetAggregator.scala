// Legacy Spark 3.x job — migrate to Spark 4 transformWithState
package com.example.fleet

import org.apache.spark.sql.{Dataset, SparkSession}
import org.apache.spark.sql.streaming.{GroupState, GroupStateTimeout, OutputMode}
import org.apache.spark.sql.functions._
import org.apache.spark.sql.types._

case class DeliveryEvent(orderId: String, eventType: String, eventTime: java.sql.Timestamp)
case class FleetSummary(orderId: String, eventCount: Int, status: String)

object LegacyFleetAggregator {
  def main(args: Array[String]): Unit = {
    val spark = SparkSession.builder().appName("legacy-fleet").getOrCreate()
    import spark.implicits._

    val schema = new StructType()
      .add("orderId", StringType)
      .add("eventType", StringType)
      .add("eventTime", TimestampType)

    val events = spark.readStream
      .format("kafka")
      .option("subscribe", "delivery-events")
      .load()
      .select(from_json(col("value").cast("string"), schema).as("data"))
      .select("data.*")
      .as[DeliveryEvent]

    val aggregated = events
      .groupByKey(_.orderId)
      .flatMapGroupsWithState[Seq[DeliveryEvent], FleetSummary](
        OutputMode.Append(),
        GroupStateTimeout.NoTimeout()
      ) { (orderId, events, state) =>
        val buffer = state.getOption.getOrElse(Seq.empty)
        var allEvents = buffer
        events.foreach { e => allEvents = allEvents :+ e }
        state.update(allEvents)

        if (allEvents.exists(_.eventType == "DELIVERED")) {
          Iterator(FleetSummary(orderId, allEvents.size, "DELIVERED"))
        } else {
          Iterator.empty
        }
      }

    aggregated.writeStream
      .format("delta")
      .option("checkpointLocation", "/tmp/fleet-checkpoint")
      .start("/mnt/delta/fleet_summary")
      .awaitTermination()
  }
}
