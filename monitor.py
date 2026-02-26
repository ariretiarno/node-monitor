#!/usr/bin/env python3

import os
import time
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, Optional
import requests
from kubernetes import client, config

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class NodeMonitor:
    def __init__(
        self,
        webhook_url: str,
        threshold_minutes: int = 5,
        check_interval_seconds: int = 60
    ):
        self.webhook_url = webhook_url
        self.threshold_minutes = threshold_minutes
        self.check_interval_seconds = check_interval_seconds
        self.node_not_ready_since: Dict[str, datetime] = {}
        self.alerted_nodes: Dict[str, bool] = {}
        
        try:
            config.load_incluster_config()
            logger.info("Loaded in-cluster Kubernetes config")
        except config.ConfigException:
            config.load_kube_config()
            logger.info("Loaded local Kubernetes config")
        
        self.v1 = client.CoreV1Api()
    
    def is_node_ready(self, node) -> bool:
        """Check if a node is in Ready state."""
        for condition in node.status.conditions:
            if condition.type == "Ready":
                return condition.status == "True"
        return False
    
    def get_node_status_message(self, node) -> str:
        """Get detailed status message from node conditions."""
        messages = []
        for condition in node.status.conditions:
            if condition.type == "Ready" and condition.status != "True":
                messages.append(f"Ready: {condition.status} - {condition.reason}: {condition.message}")
        return " | ".join(messages) if messages else "Unknown"
    
    def send_google_chat_alert(self, node_name: str, duration_minutes: float, status_message: str):
        """Send alert to Google Chat webhook."""
        message = {
            "text": f"🚨 *Node Alert*\n\n"
                   f"*Node:* `{node_name}`\n"
                   f"*Status:* Not Ready\n"
                   f"*Duration:* {duration_minutes:.1f} minutes\n"
                   f"*Details:* {status_message}\n"
                   f"*Time:* {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}"
        }
        
        try:
            response = requests.post(
                self.webhook_url,
                json=message,
                headers={"Content-Type": "application/json"},
                timeout=10
            )
            response.raise_for_status()
            logger.info(f"Alert sent successfully for node: {node_name}")
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to send alert for node {node_name}: {e}")
    
    def check_nodes(self):
        """Check all nodes and track their status."""
        try:
            nodes = self.v1.list_node()
            current_time = datetime.now()
            current_node_names = set()
            
            for node in nodes.items:
                node_name = node.metadata.name
                current_node_names.add(node_name)
                is_ready = self.is_node_ready(node)
                
                if not is_ready:
                    if node_name not in self.node_not_ready_since:
                        self.node_not_ready_since[node_name] = current_time
                        logger.warning(f"Node {node_name} is not ready. Started tracking.")
                    else:
                        not_ready_duration = current_time - self.node_not_ready_since[node_name]
                        duration_minutes = not_ready_duration.total_seconds() / 60
                        
                        if duration_minutes >= self.threshold_minutes:
                            if not self.alerted_nodes.get(node_name, False):
                                status_message = self.get_node_status_message(node)
                                logger.warning(
                                    f"Node {node_name} has been not ready for "
                                    f"{duration_minutes:.1f} minutes. Sending alert."
                                )
                                self.send_google_chat_alert(node_name, duration_minutes, status_message)
                                self.alerted_nodes[node_name] = True
                            else:
                                logger.info(
                                    f"Node {node_name} still not ready "
                                    f"({duration_minutes:.1f} minutes). Alert already sent."
                                )
                else:
                    if node_name in self.node_not_ready_since:
                        not_ready_duration = current_time - self.node_not_ready_since[node_name]
                        duration_minutes = not_ready_duration.total_seconds() / 60
                        logger.info(
                            f"Node {node_name} is now ready. "
                            f"Was not ready for {duration_minutes:.1f} minutes."
                        )
                        del self.node_not_ready_since[node_name]
                        if node_name in self.alerted_nodes:
                            del self.alerted_nodes[node_name]
            
            nodes_to_remove = set(self.node_not_ready_since.keys()) - current_node_names
            for node_name in nodes_to_remove:
                logger.info(f"Node {node_name} no longer exists. Removing from tracking.")
                del self.node_not_ready_since[node_name]
                if node_name in self.alerted_nodes:
                    del self.alerted_nodes[node_name]
            
            logger.info(
                f"Check completed. Total nodes: {len(nodes.items)}, "
                f"Not ready: {len(self.node_not_ready_since)}"
            )
            
        except Exception as e:
            logger.error(f"Error checking nodes: {e}", exc_info=True)
    
    def run(self):
        """Main monitoring loop."""
        logger.info(
            f"Starting node monitor. Threshold: {self.threshold_minutes} minutes, "
            f"Check interval: {self.check_interval_seconds} seconds"
        )
        
        while True:
            try:
                self.check_nodes()
                time.sleep(self.check_interval_seconds)
            except KeyboardInterrupt:
                logger.info("Shutting down node monitor...")
                break
            except Exception as e:
                logger.error(f"Unexpected error in main loop: {e}", exc_info=True)
                time.sleep(self.check_interval_seconds)


def main():
    webhook_url = os.getenv("GOOGLE_CHAT_WEBHOOK_URL")
    if not webhook_url:
        logger.error("GOOGLE_CHAT_WEBHOOK_URL environment variable is not set")
        exit(1)
    
    threshold_minutes = int(os.getenv("THRESHOLD_MINUTES", "5"))
    check_interval_seconds = int(os.getenv("CHECK_INTERVAL_SECONDS", "60"))
    
    monitor = NodeMonitor(
        webhook_url=webhook_url,
        threshold_minutes=threshold_minutes,
        check_interval_seconds=check_interval_seconds
    )
    
    monitor.run()


if __name__ == "__main__":
    main()
