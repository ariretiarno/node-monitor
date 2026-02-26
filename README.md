# Kubernetes Node Monitor

A continuous monitoring solution that tracks Kubernetes node health and sends alerts to Google Chat when nodes remain in a "Not Ready" state for a configurable duration.

## Features

- **Continuous Monitoring**: Long-running deployment that constantly monitors node status
- **High Availability**: 3 replicas with leader election - only one sends alerts, others standby
- **Configurable Threshold**: Set custom duration (N minutes) before alerting
- **Google Chat Integration**: Sends formatted alerts to Google Chat webhook
- **State Tracking**: Tracks node status over time and only alerts once per incident
- **Auto-Recovery Detection**: Automatically clears alerts when nodes become ready again
- **Leader Election**: Automatic failover if the active monitor pod fails
- **RBAC Compliant**: Minimal permissions (read-only access to nodes)

## Architecture

- **Deployment**: 3 replicas with leader election for high availability
- **Leader Election**: Uses Kubernetes Lease API to elect a single active monitor
- **Pod Anti-Affinity**: Spreads replicas across different nodes
- **ServiceAccount**: Dedicated service account with minimal RBAC permissions
- **ConfigMap**: Configurable threshold and check interval
- **Secret**: Secure storage for Google Chat webhook URL

## Prerequisites

- Kubernetes cluster (v1.19+)
- `kubectl` configured with cluster access
- Docker registry access (Docker Hub, GCR, ECR, etc.)
- Google Chat webhook URL

## Quick Start

### 1. Get Google Chat Webhook URL

1. Open Google Chat and go to the space where you want to receive alerts
2. Click the space name → **Apps & integrations**
3. Click **Add webhooks**
4. Name your webhook (e.g., "Node Monitor") and click **Save**
5. Copy the webhook URL

### 2. Build and Push Docker Image

```bash
# Navigate to project directory
cd /Users/ariretiarno/CascadeProjects/k8s-node-monitor

# Build the Docker image
docker build -t your-registry/node-monitor:latest .

# Push to your registry
docker push your-registry/node-monitor:latest
```

**Note**: Replace `your-registry` with your actual registry (e.g., `docker.io/username`, `gcr.io/project-id`, etc.)

### 3. Create Secret with Webhook URL

```bash
# Copy the example secret file
cp k8s/secret.yaml.example k8s/secret.yaml

# Edit the secret file and replace with your actual webhook URL
# Edit k8s/secret.yaml and replace the GOOGLE_CHAT_WEBHOOK_URL value
```

**Important**: Add `k8s/secret.yaml` to `.gitignore` to avoid committing sensitive data:

```bash
echo "k8s/secret.yaml" >> .gitignore
```

### 4. Configure Monitoring Parameters (Optional)

Edit `k8s/configmap.yaml` to adjust:

- **THRESHOLD_MINUTES**: Duration before alerting (default: 5 minutes)
- **CHECK_INTERVAL_SECONDS**: How often to check nodes (default: 60 seconds)

```yaml
data:
  THRESHOLD_MINUTES: "10"        # Alert after 10 minutes
  CHECK_INTERVAL_SECONDS: "120"  # Check every 2 minutes
```

### 5. Update Deployment Image

Edit `k8s/deployment.yaml` and update the image reference:

```yaml
spec:
  template:
    spec:
      containers:
      - name: monitor
        image: your-registry/node-monitor:latest  # Update this line
```

### 6. Deploy to Kubernetes

```bash
# Apply all manifests
kubectl apply -f k8s/namespace.yaml
kubectl apply -f k8s/serviceaccount.yaml
kubectl apply -f k8s/clusterrole.yaml
kubectl apply -f k8s/clusterrolebinding.yaml
kubectl apply -f k8s/configmap.yaml
kubectl apply -f k8s/secret.yaml
kubectl apply -f k8s/deployment.yaml

# Or apply all at once
kubectl apply -f k8s/
```

### 7. Verify Deployment

```bash
# Check pod status (should see 3 replicas)
kubectl get pods -n node-monitor

# View logs from all pods
kubectl logs -n node-monitor -l app=node-monitor -f

# Check which pod is the leader
kubectl logs -n node-monitor -l app=node-monitor --tail=20 | grep -E "LEADER|FOLLOWER"

# Check the lease
kubectl get lease -n node-monitor node-monitor-lease -o yaml

# Check if monitor is running
kubectl get deployment -n node-monitor
```

You should see output like:
```
🎯 I am the LEADER. Starting monitoring.
⏸️  I am a FOLLOWER. Waiting for leadership.
⏸️  I am a FOLLOWER. Waiting for leadership.
```

## High Availability & Leader Election

### How It Works

1. **3 Replicas**: The deployment runs 3 pods across different nodes (via pod anti-affinity)
2. **Leader Election**: Pods use Kubernetes Lease API to elect one leader
3. **Active Monitoring**: Only the leader performs checks and sends alerts
4. **Automatic Failover**: If the leader pod fails, another pod takes over within ~15 seconds
5. **No Duplicate Alerts**: Only one pod sends alerts at any time

### Leader Election Behavior

- **Lease Duration**: 15 seconds
- **Renewal**: Leader renews lease every check interval
- **Takeover**: If leader doesn't renew, another pod acquires the lease
- **Identity**: Each pod uses its pod name as identity

### Verifying Leader Election

```bash
# Watch leader changes in real-time
kubectl logs -n node-monitor -l app=node-monitor -f | grep -E "LEADER|FOLLOWER|leadership"

# Check current lease holder
kubectl get lease -n node-monitor node-monitor-lease -o jsonpath='{.spec.holderIdentity}'

# Test failover by deleting the leader pod
LEADER=$(kubectl get lease -n node-monitor node-monitor-lease -o jsonpath='{.spec.holderIdentity}')
kubectl delete pod -n node-monitor $LEADER

# Watch another pod take over leadership
kubectl logs -n node-monitor -l app=node-monitor -f
```

## Configuration

### Environment Variables

| Variable | Description | Default | Source |
|----------|-------------|---------|--------|
| `GOOGLE_CHAT_WEBHOOK_URL` | Google Chat webhook URL | Required | Secret |
| `THRESHOLD_MINUTES` | Minutes before alerting | 5 | ConfigMap |
| `CHECK_INTERVAL_SECONDS` | Seconds between checks | 60 | ConfigMap |
| `ENABLE_LEADER_ELECTION` | Enable leader election | true | Deployment |
| `NAMESPACE` | Namespace for lease | Auto | Deployment |
| `POD_NAME` | Pod name for identity | Auto | Deployment |

### Adjusting Configuration

To change configuration without redeploying:

```bash
# Edit ConfigMap
kubectl edit configmap node-monitor-config -n node-monitor

# Restart deployment to pick up changes
kubectl rollout restart deployment/node-monitor -n node-monitor
```

## Alert Format

When a node is not ready for N minutes, you'll receive a Google Chat message like:

```
🚨 Node Alert

Node: `worker-node-1`
Status: Not Ready
Duration: 5.2 minutes
Details: Ready: False - NodeNotReady: Node is not ready
Time: 2026-02-26 12:55:30 UTC
```

## Monitoring Behavior

1. **Initial Detection**: When a node becomes "Not Ready", the monitor starts tracking it
2. **Threshold Check**: Every check interval, it calculates how long the node has been not ready
3. **Alert Trigger**: Once the threshold is exceeded, an alert is sent to Google Chat
4. **Single Alert**: Only one alert is sent per incident (no spam)
5. **Recovery**: When the node becomes ready again, tracking is cleared and ready for next incident

## Troubleshooting

### Pod Not Starting

```bash
# Check pod events
kubectl describe pod -n node-monitor -l app=node-monitor

# Check logs
kubectl logs -n node-monitor -l app=node-monitor
```

### No Alerts Being Sent

1. Verify webhook URL is correct:
   ```bash
   kubectl get secret node-monitor-secret -n node-monitor -o jsonpath='{.data.GOOGLE_CHAT_WEBHOOK_URL}' | base64 -d
   ```

2. Test webhook manually:
   ```bash
   curl -X POST "YOUR_WEBHOOK_URL" \
     -H "Content-Type: application/json" \
     -d '{"text": "Test message"}'
   ```

3. Check monitor logs for errors:
   ```bash
   kubectl logs -n node-monitor -l app=node-monitor --tail=100
   ```

### RBAC Permission Issues

```bash
# Verify ClusterRole is created
kubectl get clusterrole node-monitor

# Verify ClusterRoleBinding
kubectl get clusterrolebinding node-monitor

# Test permissions
kubectl auth can-i list nodes --as=system:serviceaccount:node-monitor:node-monitor
```

## Local Testing

To test the monitor locally (outside Kubernetes):

```bash
# Install dependencies
pip install -r requirements.txt

# Set environment variables
export GOOGLE_CHAT_WEBHOOK_URL="your-webhook-url"
export THRESHOLD_MINUTES="5"
export CHECK_INTERVAL_SECONDS="60"

# Run monitor (requires local kubeconfig)
python monitor.py
```

## Uninstall

```bash
# Delete all resources
kubectl delete -f k8s/

# Or delete namespace (removes everything)
kubectl delete namespace node-monitor
```

## Security Considerations

- Monitor runs as non-root user (UID 65534)
- Read-only root filesystem
- Minimal RBAC permissions (only read nodes)
- Webhook URL stored in Kubernetes Secret
- No privilege escalation allowed

## Customization

### Change Namespace

To deploy in a different namespace, update the `namespace` field in all manifests:

```bash
# Using sed (macOS)
sed -i '' 's/namespace: node-monitor/namespace: your-namespace/g' k8s/*.yaml

# Using sed (Linux)
sed -i 's/namespace: node-monitor/namespace: your-namespace/g' k8s/*.yaml
```

### Add More Alert Channels

Modify `monitor.py` to add additional alert methods (Slack, email, PagerDuty, etc.) in the `send_google_chat_alert` method.

## License

MIT

## Contributing

Feel free to submit issues and enhancement requests!
