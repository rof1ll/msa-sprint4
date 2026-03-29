import asyncio
import os
import threading
import uuid
from datetime import datetime, timezone

from flask import Flask, jsonify, request
from pyzeebe import Job, ZeebeClient, ZeebeWorker, create_insecure_channel

PORT = int(os.getenv("PORT", "3000"))
ZEEBE_ADDRESS = os.getenv("ZEEBE_ADDRESS", "127.0.0.1:26500")
PROCESS_ID = os.getenv("PROCESS_ID", "payment-saga-demo")
BOOTSTRAP_SCENARIOS = [item.strip() for item in os.getenv("BOOTSTRAP_SCENARIOS", "").split(",") if item.strip()]
BOOTSTRAP_DELAY_MS = int(os.getenv("BOOTSTRAP_DELAY_MS", "10000"))

app = Flask(__name__)
worker_loop = asyncio.new_event_loop()
worker_ready = threading.Event()
worker_ref = None
client_ref = None


def log(message: str, payload=None) -> None:
    timestamp = datetime.now(timezone.utc).isoformat()
    if payload is None:
        print(f"[{timestamp}] {message}", flush=True)
    else:
        print(f"[{timestamp}] {message} {payload}", flush=True)


def safe_manual_review_decision(value: str | None) -> str:
    return "reject" if value == "reject" else "approve"


def build_process_variables(payload: dict) -> dict:
    return {
        "orderId": payload.get("orderId") or str(uuid.uuid4()),
        "amount": payload.get("amount", 100),
        "currency": payload.get("currency", "RUB"),
        "scenario": payload.get("scenario", "approve"),
        "manualReviewDecision": safe_manual_review_decision(payload.get("manualReviewDecision")),
    }


async def on_error(exception: Exception, job: Job) -> None:
    log("worker:error", {"job_key": job.key, "type": job.type, "error": str(exception)})
    await job.set_error_status(f"Handler error: {exception}")


def register_tasks(worker: ZeebeWorker) -> None:
    @worker.task(task_type="start-saga", exception_handler=on_error)
    def start_saga(orderId=None, scenario=None, amount=100, currency="RUB"):
        result = {
            "orderId": orderId,
            "scenario": scenario,
            "amount": amount,
            "currency": currency,
            "sagaStatus": "STARTED",
            "startedAt": datetime.now(timezone.utc).isoformat(),
        }
        log("worker:start-saga", result)
        return result

    @worker.task(task_type="create-payment", exception_handler=on_error)
    def create_payment(orderId=None, scenario=None, paymentId=None):
        result = {
            "orderId": orderId,
            "paymentId": paymentId or f"pay-{orderId}",
            "scenario": scenario,
            "paymentStatus": "CREATED",
            "createdAt": datetime.now(timezone.utc).isoformat(),
        }
        log("worker:create-payment", result)
        return result

    @worker.task(task_type="debit-customer", exception_handler=on_error)
    def debit_customer(orderId=None, paymentId=None, scenario=None, amount=100, currency="RUB"):
        result = {
            "orderId": orderId,
            "paymentId": paymentId,
            "scenario": scenario,
            "amount": amount,
            "currency": currency,
            "debitStatus": "DEBITED",
        }
        log("worker:debit-customer", result)
        return result

    @worker.task(task_type="run-fraud-check", exception_handler=on_error)
    def run_fraud_check(orderId=None, paymentId=None, scenario="approve", manualReviewDecision="approve"):
        if scenario not in {"approve", "reject", "manual_review"}:
            raise ValueError(f"Unsupported scenario: {scenario}")

        result = {
            "orderId": orderId,
            "paymentId": paymentId,
            "scenario": scenario,
            "fraudResult": scenario,
            "fraudCheckedAt": datetime.now(timezone.utc).isoformat(),
            "manualReviewDecision": safe_manual_review_decision(manualReviewDecision),
        }
        log("worker:run-fraud-check", result)
        return result

    @worker.task(task_type="start-manual-review", exception_handler=on_error)
    def start_manual_review(orderId=None, paymentId=None, scenario=None):
        result = {
            "orderId": orderId,
            "paymentId": paymentId,
            "scenario": scenario,
            "paymentStatus": "WAITING_MANUAL_REVIEW",
            "manualReviewStartedAt": datetime.now(timezone.utc).isoformat(),
        }
        log("worker:start-manual-review", result)
        return result

    @worker.task(task_type="prepare-manual-review", exception_handler=on_error)
    def prepare_manual_review(orderId=None, paymentId=None, scenario=None):
        result = {
            "orderId": orderId,
            "paymentId": paymentId,
            "scenario": scenario,
            "manualReviewPreparationStatus": "CREATED",
        }
        log("worker:prepare-manual-review", result)
        return result

    @worker.task(task_type="fraud-approved", exception_handler=on_error)
    def fraud_approved(orderId=None, paymentId=None, scenario=None):
        result = {
            "orderId": orderId,
            "paymentId": paymentId,
            "scenario": scenario,
            "fraudDecisionRecorded": "APPROVED",
        }
        log("worker:fraud-approved", result)
        return result

    @worker.task(task_type="fraud-rejected", exception_handler=on_error)
    def fraud_rejected(orderId=None, paymentId=None, scenario=None):
        result = {
            "orderId": orderId,
            "paymentId": paymentId,
            "scenario": scenario,
            "fraudDecisionRecorded": "REJECTED",
        }
        log("worker:fraud-rejected", result)
        return result

    @worker.task(task_type="manual-approve", exception_handler=on_error)
    def manual_approve(orderId=None, paymentId=None, scenario=None):
        result = {
            "orderId": orderId,
            "paymentId": paymentId,
            "scenario": scenario,
            "manualDecisionRecorded": "APPROVED",
        }
        log("worker:manual-approve", result)
        return result

    @worker.task(task_type="manual-reject", exception_handler=on_error)
    def manual_reject(orderId=None, paymentId=None, scenario=None):
        result = {
            "orderId": orderId,
            "paymentId": paymentId,
            "scenario": scenario,
            "manualDecisionRecorded": "REJECTED",
        }
        log("worker:manual-reject", result)
        return result

    @worker.task(task_type="timeout-marker", exception_handler=on_error)
    def timeout_marker(orderId=None, paymentId=None, scenario=None):
        result = {
            "orderId": orderId,
            "paymentId": paymentId,
            "scenario": scenario,
            "timeoutRecorded": True,
        }
        log("worker:timeout-marker", result)
        return result

    @worker.task(task_type="apply-cutoff-approval", exception_handler=on_error)
    def apply_cutoff_approval(orderId=None, paymentId=None, scenario=None):
        result = {
            "orderId": orderId,
            "paymentId": paymentId,
            "scenario": scenario,
            "fraudResult": "approve",
            "paymentStatus": "AUTO_APPROVED_BY_CUTOFF",
            "manualReviewTimedOut": True,
        }
        log("worker:apply-cutoff-approval", result)
        return result

    @worker.task(task_type="transfer-to-merchant", exception_handler=on_error)
    def transfer_to_merchant(orderId=None, paymentId=None, scenario=None):
        result = {
            "orderId": orderId,
            "paymentId": paymentId,
            "scenario": scenario,
            "transferStatus": "TRANSFERRED",
            "transferredAt": datetime.now(timezone.utc).isoformat(),
        }
        log("worker:transfer-to-merchant", result)
        return result

    @worker.task(task_type="mark-success", exception_handler=on_error)
    def mark_success(orderId=None, paymentId=None, scenario=None):
        result = {
            "orderId": orderId,
            "paymentId": paymentId,
            "scenario": scenario,
            "paymentStatus": "SUCCEEDED",
        }
        log("worker:mark-success", result)
        return result

    @worker.task(task_type="notify-customer", exception_handler=on_error)
    def notify_customer(orderId=None, paymentId=None, scenario=None, paymentStatus=None):
        notification_type = "PAYMENT_SUCCEEDED" if paymentStatus == "SUCCEEDED" else "PAYMENT_REJECTED_OR_REFUNDED"
        result = {
            "orderId": orderId,
            "paymentId": paymentId,
            "scenario": scenario,
            "customerNotificationStatus": "SENT",
            "customerNotificationType": notification_type,
        }
        log("worker:notify-customer", result)
        return result

    @worker.task(task_type="refund-customer", exception_handler=on_error)
    def refund_customer(orderId=None, paymentId=None, scenario=None):
        result = {
            "orderId": orderId,
            "paymentId": paymentId,
            "scenario": scenario,
            "refundStatus": "REFUNDED",
            "refundedAt": datetime.now(timezone.utc).isoformat(),
        }
        log("worker:refund-customer", result)
        return result

    @worker.task(task_type="mark-rejected", exception_handler=on_error)
    def mark_rejected(orderId=None, paymentId=None, scenario=None):
        result = {
            "orderId": orderId,
            "paymentId": paymentId,
            "scenario": scenario,
            "paymentStatus": "REJECTED",
        }
        log("worker:mark-rejected", result)
        return result

    @worker.task(task_type="send-security-alert", exception_handler=on_error)
    def send_security_alert(orderId=None, paymentId=None, scenario=None):
        result = {
            "orderId": orderId,
            "paymentId": paymentId,
            "scenario": scenario,
            "securityAlertStatus": "SENT",
        }
        log("worker:send-security-alert", result)
        return result


async def start_process_instance(payload: dict) -> int:
    variables = build_process_variables(payload)
    response = await client_ref.run_process(
        bpmn_process_id=PROCESS_ID,
        variables=variables,
    )
    process_instance_key = getattr(response, "process_instance_key", response)
    log("process-instance:started", {"processInstanceKey": process_instance_key, "variables": variables})
    return process_instance_key


async def bootstrap_demo_instances() -> None:
    if not BOOTSTRAP_SCENARIOS:
        log("bootstrap:skipped")
        return

    await asyncio.sleep(BOOTSTRAP_DELAY_MS / 1000)

    for scenario in BOOTSTRAP_SCENARIOS:
        started = False
        while not started:
            try:
                await start_process_instance(
                    {
                        "scenario": scenario,
                        "amount": 1000,
                        "currency": "RUB",
                        "manualReviewDecision": "approve",
                    }
                )
                started = True
            except Exception as exc:  # noqa: BLE001
                log("bootstrap:retry", {"scenario": scenario, "error": str(exc)})
                await asyncio.sleep(5)


async def worker_main() -> None:
    global worker_ref, client_ref

    channel = create_insecure_channel(grpc_address=ZEEBE_ADDRESS)
    worker_ref = ZeebeWorker(channel, max_connection_retries=-1)
    client_ref = ZeebeClient(channel)
    register_tasks(worker_ref)
    worker_ready.set()

    log("zeebe:worker-ready", {"zeebeAddress": ZEEBE_ADDRESS, "processId": PROCESS_ID})
    asyncio.create_task(bootstrap_demo_instances())
    await worker_ref.work()


def worker_thread_target() -> None:
    asyncio.set_event_loop(worker_loop)
    worker_loop.run_until_complete(worker_main())


@app.get("/health")
def health():
    return jsonify(
        {
            "ok": True,
            "workerReady": worker_ready.is_set(),
            "zeebeAddress": ZEEBE_ADDRESS,
            "processId": PROCESS_ID,
        }
    )


@app.post("/start")
def start():
    if not worker_ready.is_set():
        return jsonify({"error": "worker is not ready yet"}), 503

    payload = request.get_json(silent=True) or {}
    future = asyncio.run_coroutine_threadsafe(start_process_instance(payload), worker_loop)

    try:
        process_instance_key = future.result(timeout=15)
    except Exception as exc:  # noqa: BLE001
        return jsonify({"error": str(exc)}), 500

    return jsonify({"processInstanceKey": process_instance_key, "processId": PROCESS_ID}), 201


if __name__ == "__main__":
    log("http:listening", {"port": PORT})
    threading.Thread(target=worker_thread_target, daemon=True).start()
    app.run(host="0.0.0.0", port=PORT)
