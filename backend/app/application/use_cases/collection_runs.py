"""Use case'ler: koleksiyonu çalıştırma.

Adımlar sırayla çalışır. Her adımdan sonra:
1. API'nin kuralları cevaba uygulanır (test motoru)
2. Adımın "değişken çıkarma" ayarlarıyla cevaptan değerler alınır ve sonraki adımlarda
   {{değişken}} olarak kullanılabilir (ortam değişkeniyle aynı adı taşırsa onu ezer)
3. Sonuç test geçmişine kaydedilir ve çalıştırma kaydı güncellenir; böylece arayüz
   çalışma sürerken ilerlemeyi (1/3, 2/3...) canlı görebilir

stop_on_failure açıksa geçemeyen ilk adımdan sonra kalanlar "skipped" olur.

İki yoldan çalışır:
- Hemen:       RunCollection doğrudan çağrılır
- Kuyruktan:   "queued" kayıt oluşur, worker ExecuteQueuedRun ile çalıştırır
"""

import logging
import time
from dataclasses import dataclass, field

from app.application.ports.collections import (
    CollectionRepository,
    CollectionRunRepository,
    RunNotifier,
)
from app.application.ports.environments import EnvironmentRepository
from app.application.ports.security import Cipher
from app.application.ports.testing import ApiSender, ApiTestRunRepository
from app.application.use_cases.environments import GetEnvironment
from app.domain.collections import (
    SOURCE_TYPES,
    Collection,
    CollectionRun,
    ExtractedValue,
    Extraction,
    RunState,
    StepResult,
    extract_value,
    shown_value,
)
from app.domain.errors import NotFound, ProductionConfirmationRequired, SecretUnreadable
from app.domain.testing.engine import evaluate
from app.domain.testing.rules import RuleResult
from app.domain.testing.runs import ApiTestRun, SendOutcome, run_status

logger = logging.getLogger(__name__)


@dataclass
class RunContext:
    """Çalıştırma boyunca kullanılan değişkenler ve maskelenecek gizli değerler."""

    variables: dict[str, str] = field(default_factory=dict)
    secrets: list[str] = field(default_factory=list)
    environment_name: str | None = None


class PrepareCollectionRun:
    """Ortam değişkenlerini yükler ve Production kuralını uygular."""

    def __init__(self, environments: EnvironmentRepository, cipher: Cipher) -> None:
        self._environments = environments
        self._cipher = cipher

    def __call__(
        self, collection: Collection, environment_id: int | None, confirm_production: bool
    ) -> RunContext:
        context = RunContext()
        if environment_id is None:
            return context

        environment = GetEnvironment(self._environments)(environment_id)
        context.environment_name = environment.name
        context.variables, context.secrets = environment.resolve_variables(self._cipher.decrypt)
        collection.ensure_production_confirmed(environment, confirm_production)
        return context


class RunCollection:
    def __init__(
        self,
        sender: ApiSender,
        test_runs: ApiTestRunRepository,
        runs: CollectionRunRepository,
        cipher: Cipher,
        notifier: RunNotifier,
    ) -> None:
        self._sender = sender
        self._test_runs = test_runs
        self._runs = runs
        self._cipher = cipher
        self._notifier = notifier

    def __call__(
        self,
        collection: Collection,
        context: RunContext,
        user_id: int | None,
        collection_run: CollectionRun | None = None,
    ) -> CollectionRun:
        """Koleksiyonu baştan sona çalıştırır. collection_run verilirse (kuyruktan gelen)
        onu günceller, verilmezse yeni bir kayıt oluşturur."""
        started = time.perf_counter()
        variables = dict(context.variables)
        secrets = list(context.secrets)

        if collection_run is None:
            collection_run = CollectionRun.new(collection, RunState.RUNNING, user_id=user_id)
        collection_run.start(collection, context.environment_name)
        self._runs.save(collection_run)  # id gerekiyor ve arayüz "çalışıyor" durumunu görsün

        steps: list[StepResult] = []
        stop = False
        for item in collection.enabled_items:
            api = item.api
            if stop or api is None:
                steps.append(
                    StepResult(
                        position=item.position,
                        api_definition_id=item.api_definition_id,
                        api_name=api.name if api else "(silinmiş API)",
                        method=api.method.value if api else "-",
                        status="skipped" if stop else "error",
                        message=(
                            "Önceki adım geçemediği için çalıştırılmadı"
                            if stop
                            else "Bu adımın API tanımı silinmiş"
                        ),
                    )
                )
                stop = stop or collection.stop_on_failure
                collection_run.record_progress(steps)
                self._runs.save(collection_run)
                continue

            try:
                auth = api.stored_auth(self._cipher.decrypt)
            except SecretUnreadable:
                auth = {}
            outcome = self._sender.send(
                api,
                auth,
                variables=variables,
                secrets=secrets,
                environment_name=context.environment_name,
            )
            rule_results = evaluate(api.assertions or [], outcome, variables)
            extracted, missing = _extract(item.extractions or [], outcome, variables, secrets)
            rule_results += missing

            test_run = ApiTestRun.record(
                api=api,
                outcome=outcome,
                results=rule_results,
                triggered_by_id=user_id,
                collection_run_id=collection_run.id,
                secrets=secrets,
            )
            self._test_runs.add(test_run)
            status = run_status(outcome, rule_results).value
            steps.append(
                StepResult(
                    position=item.position,
                    api_definition_id=api.id,
                    api_name=api.name,
                    method=api.method.value,
                    status=status,
                    test_run_id=test_run.id,
                    message=outcome.error,
                    extracted=extracted,
                )
            )
            if status != "passed" and collection.stop_on_failure:
                stop = True
            collection_run.record_progress(steps)
            self._runs.save(collection_run)  # canlı izleme: her adımdan sonra ilerleme görünsün

        collection_run.complete(steps, round((time.perf_counter() - started) * 1000, 1))
        self._runs.save(collection_run)
        self._notifier.notify(collection_run)
        return collection_run


def _extract(
    raw_extractions: list[dict],
    outcome: SendOutcome,
    variables: dict[str, str],
    secrets: list[str],
) -> tuple[list[ExtractedValue], list[RuleResult]]:
    """Cevaptan değişkenleri alır; bulunanlar sonraki adımlar için variables'a yazılır.

    Bulunamayan değer adımı "kaldı" yapar: nedeni kural sonuçlarına eklenir.
    """
    extracted: list[ExtractedValue] = []
    missing: list[RuleResult] = []
    for raw in raw_extractions:
        extraction = Extraction.from_dict(raw)
        value = extract_value(extraction, outcome)
        if value is None:
            extracted.append(ExtractedValue(variable=extraction.variable, found=False))
            if outcome.ok:
                missing.append(
                    RuleResult(
                        type=SOURCE_TYPES[extraction.source],
                        target=extraction.path,
                        operator="extract",
                        expected=f"{{{{{extraction.variable}}}}}",
                        passed=False,
                        message=f"'{extraction.variable}' değişkeni cevaptan alınamadı",
                    )
                )
            continue
        variables[extraction.variable] = value
        if extraction.secret and value:
            secrets.append(value)
        extracted.append(
            ExtractedValue(
                variable=extraction.variable,
                found=True,
                value=shown_value(value, extraction.secret),
            )
        )
    return extracted, missing


class ExecuteQueuedRun:
    """Kuyruktaki bir çalıştırmayı yürütür (worker bunu çağırır).

    Aynı kayıt iki kez gelirse (ör. worker yeniden başladı) ikinci sefer bir şey yapmaz.
    """

    def __init__(
        self,
        collections: CollectionRepository,
        runs: CollectionRunRepository,
        prepare: PrepareCollectionRun,
        run_collection: RunCollection,
        notifier: RunNotifier,
    ) -> None:
        self._collections = collections
        self._runs = runs
        self._prepare = prepare
        self._run_collection = run_collection
        self._notifier = notifier

    def __call__(
        self, run_id: int, environment_id: int | None, confirm_production: bool
    ) -> CollectionRun | None:
        collection_run = self._runs.get(run_id)
        if collection_run is None:
            logger.warning("Çalıştırma kaydı bulunamadı: %s", run_id)
            return None
        if collection_run.state != RunState.QUEUED.value:
            return collection_run

        collection = (
            self._collections.get(collection_run.collection_id)
            if collection_run.collection_id
            else None
        )
        if collection is None:
            return self._fail(collection_run, "Koleksiyon silinmiş", notify=False)

        try:
            context = self._prepare(collection, environment_id, confirm_production)
        except (NotFound, ProductionConfirmationRequired) as exc:
            return self._fail(collection_run, exc.message)

        try:
            return self._run_collection(
                collection, context, collection_run.triggered_by_id, collection_run=collection_run
            )
        except Exception as exc:  # worker çökmesin, kayıt "çalışıyor"da takılı kalmasın
            logger.exception("Koleksiyon çalıştırması başarısız: %s", run_id)
            self._runs.discard_changes()
            return self._fail(self._runs.get(run_id), f"Beklenmeyen hata: {exc}")

    def _fail(self, run: CollectionRun, message: str, notify: bool = True) -> CollectionRun:
        run.fail(message)
        self._runs.save(run)
        if notify:
            self._notifier.notify(run)
        return run
