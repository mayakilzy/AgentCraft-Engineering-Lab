/**
 * Static fallback experiment data — used when the backend is unavailable
 * so the UI can still render the 10-experiment gallery in PREVIEW mode.
 *
 * IDs MUST match lab-modules/*.yaml exactly so the same fallback works
 * for both the manifest endpoint and the experiments list.
 *
 * Per the architecture contract §1 + A09: cards surface level,
 * prerequisites, expected outputs, technologies. No code execution.
 */
import type { ExperimentManifest } from '../api/client';

/**
 * FALLBACK_MANIFESTS — minimal but contract-complete manifests for
 * all 10 canonical experiments. Each has at least one step so the
 * Workbench stepper renders something useful in preview mode.
 */
export const FALLBACK_MANIFESTS: ExperimentManifest[] = [
  {
    id: 'graph-first-network',
    version: '1.1.0',
    module_id: 'graph',
    level: 'beginner',
    estimated_minutes: 20,
    title: { en: 'Build Your First Graph', ar: 'أنشئ أول شبكة علاقات' },
    description: {
      en: 'Model five tools as nodes and connect them with directed edges. Inspect the visualization and validate endpoint integrity.',
      ar: 'مثّل خمس أدوات كعقد واربطها بحواف موجّهة. افحص التصور وتحقق من سلامة النهايات.',
    },
    technology: ['NetworkX', 'PostgreSQL', 'Cytoscape.js'],
    prerequisites: [],
    dataset_key: 'starter-five-v1',
    required_services: ['postgres'],
    capabilities: ['graph-visualization'],
    public_demo_enabled: true,
    steps: [
      {
        id: 'seed',
        title: { en: 'Load dataset', ar: 'تحميل البيانات' },
        instruction: {
          en: 'Load the fixed sample of five tool nodes.',
          ar: 'حمّل العقد التجريبية الثابتة (خمس أدوات).',
        },
        operation_key: 'seed_graph',
        input_schema_ref: 'seed_graph_v1',
        validator_key: 'seed_five_nodes_v1',
        expected: { node_count: 5, edge_count: 4 },
      },
      {
        id: 'inspect',
        title: { en: 'Inspect nodes', ar: 'افحص العقد' },
        instruction: {
          en: 'List the seeded nodes and confirm five tools are present.',
          ar: 'استعرض العقد المُحمّلة وتأكد من وجود خمس أدوات.',
        },
        operation_key: 'graph_metrics',
        input_schema_ref: 'graph_metrics_v1',
        validator_key: 'seed_five_nodes_v1',
        expected: { node_count: 5, edge_count: 4 },
      },
      {
        id: 'visualize',
        title: { en: 'Inspect visualization', ar: 'افحص التصور' },
        instruction: {
          en: 'Open the Graph Explorer and confirm directed edges point consumer → provider.',
          ar: 'افتح عارض الرسم وتأكد أن الحواف الموجّهة تشير من المستهلك إلى المُوفّر.',
        },
        operation_key: 'graph_metrics',
        input_schema_ref: 'graph_metrics_v1',
        validator_key: 'seed_five_nodes_v1',
        expected: { node_count: 5, edge_count: 4 },
      },
    ],
    failure_mode: 'Seeding an unknown fixture key produces NotFoundError.',
  },
  {
    id: 'shortest-path',
    version: '1.1.0',
    module_id: 'graph',
    level: 'beginner',
    estimated_minutes: 20,
    title: { en: 'Shortest Path', ar: 'أقصر مسار' },
    description: {
      en: 'Select an application and a target dependency; find the shortest directed path between them and verify unreachable handling.',
      ar: 'اختر تطبيقاً وتبعية هدف؛ اعثر على أقصر مسار موجّه بينهما وتحقق من معالجة حالة عدم الوصول.',
    },
    technology: ['NetworkX'],
    prerequisites: ['graph-first-network'],
    dataset_key: 'directed-path-v1',
    required_services: ['postgres'],
    capabilities: ['graph-visualization'],
    public_demo_enabled: true,
    steps: [
      {
        id: 'seed',
        title: { en: 'Load directed path fixture', ar: 'حمّل بيانات المسار الموجّه' },
        instruction: {
          en: 'Load the directed-path fixture (apps and tools with directed edges).',
          ar: 'حمّل بيانات المسار الموجّه (تطبيقات وأدوات بحواف موجّهة).',
        },
        operation_key: 'seed_graph',
        input_schema_ref: 'seed_graph_v1',
        validator_key: 'seed_five_nodes_v1',
        expected: { node_count: 5 },
      },
      {
        id: 'compute',
        title: { en: 'Compute shortest path', ar: 'احسب أقصر مسار' },
        instruction: {
          en: 'Compute the directed shortest path from source to target.',
          ar: 'احسب أقصر مسار موجّه من المصدر إلى الهدف.',
        },
        operation_key: 'shortest_path',
        input_schema_ref: 'shortest_path_v1',
        validator_key: 'shortest_path_v1',
        expected: { path: ['A', 'B'] },
      },
      {
        id: 'unreachable',
        title: { en: 'Verify unreachable handling', ar: 'تحقق من معالجة عدم الوصول' },
        instruction: {
          en: 'Confirm a non-reachable target returns null path with a clear message.',
          ar: 'تأكد أن هدف غير قابل للوصول يُرجع مساراً فارغاً برسالة واضحة.',
        },
        operation_key: 'shortest_path',
        input_schema_ref: 'shortest_path_v1',
        validator_key: 'shortest_path_v1',
        expected: { path: null },
      },
    ],
  },
  {
    id: 'interactive-explorer',
    version: '1.1.0',
    module_id: 'graph',
    level: 'beginner',
    estimated_minutes: 25,
    title: { en: 'Interactive Graph Explorer', ar: 'استكشاف الرسم تفاعلياً' },
    description: {
      en: 'Load a mixed-kind graph, change the layout, filter by kind and inspect node/edge details. Confirm the original data is unaffected.',
      ar: 'حمّل رسماً مختلط الأنواع، غيّر التخطيط، صفِ حسب النوع وافحص تفاصيل العقد والحواف. أكّد أن البيانات الأصلية لم تتأثر.',
    },
    technology: ['Cytoscape.js'],
    prerequisites: ['graph-first-network'],
    dataset_key: 'mixed-kind-v1',
    required_services: ['postgres'],
    capabilities: ['graph-visualization'],
    public_demo_enabled: true,
    steps: [
      {
        id: 'load',
        title: { en: 'Load mixed-kind fixture', ar: 'حمّل بيانات الأنواع المختلطة' },
        instruction: {
          en: 'Load the mixed-kind fixture (apps, tools, skills).',
          ar: 'حمّل بيانات الأنواع المختلطة (تطبيقات وأدوات ومهارات).',
        },
        operation_key: 'seed_graph',
        input_schema_ref: 'seed_graph_v1',
        validator_key: 'seed_mixed_v1',
        expected: { node_count: 8 },
      },
      {
        id: 'layout',
        title: { en: 'Switch layouts', ar: 'بدّل التخطيطات' },
        instruction: {
          en: 'Cycle through grid, circle, concentric and breadthfirst layouts.',
          ar: 'بدّل بين تخطيطات الشبكة والدائرة والمتحدة المركز واتساع أولاً.',
        },
        operation_key: 'graph_metrics',
        input_schema_ref: 'graph_metrics_v1',
        validator_key: 'seed_mixed_v1',
        expected: { node_count: 8 },
      },
      {
        id: 'filter',
        title: { en: 'Filter by kind', ar: 'صفِّ حسب النوع' },
        instruction: {
          en: 'Toggle kind chips and confirm the view filters without mutating the graph.',
          ar: 'بدّل رقائق النوع وتأكد أن العرض يُصفّى دون تغيير الرسم.',
        },
        operation_key: 'graph_metrics',
        input_schema_ref: 'graph_metrics_v1',
        validator_key: 'seed_mixed_v1',
        expected: { node_count: 8 },
      },
    ],
  },
  {
    id: 'sql-vs-cypher',
    version: '1.1.0',
    module_id: 'parity',
    level: 'intermediate',
    estimated_minutes: 25,
    title: { en: 'SQL versus Cypher', ar: 'SQL مقابل Cypher' },
    description: {
      en: 'Answer the same dependency query from two engines. Compare canonical result sets (order-independent) and inspect timing context.',
      ar: 'أجب عن استعلام التبعيات نفسه من محركين. قارن مجموعات النتائج (بغض النظر عن الترتيب) وافحص سياق التوقيت.',
    },
    technology: ['PostgreSQL', 'Neo4j'],
    prerequisites: ['graph-first-network'],
    dataset_key: 'parity-v1',
    required_services: ['postgres', 'neo4j'],
    capabilities: ['graph-visualization'],
    public_demo_enabled: true,
    steps: [
      {
        id: 'seed',
        title: { en: 'Load parity fixture', ar: 'حمّل بيانات المقارنة' },
        instruction: {
          en: 'Load the parity fixture into both engines.',
          ar: 'حمّل بيانات المقارنة في كلا المحركين.',
        },
        operation_key: 'seed_graph',
        input_schema_ref: 'seed_graph_v1',
        validator_key: 'seed_parity_v1',
        expected: { node_count: 6 },
      },
      {
        id: 'query-sql',
        title: { en: 'Query via SQL', ar: 'استعلم عبر SQL' },
        instruction: {
          en: 'Run the recursive SQL dependency query.',
          ar: 'شغّل استعلام SQL التبعيات العودي.',
        },
        operation_key: 'query_sql',
        input_schema_ref: 'query_parity_v1',
        validator_key: 'parity_canonical_v1',
        expected: { rows: 4 },
      },
      {
        id: 'query-cypher',
        title: { en: 'Query via Cypher', ar: 'استعلم عبر Cypher' },
        instruction: {
          en: 'Run the equivalent Cypher query.',
          ar: 'شغّل استعلام Cypher المكافئ.',
        },
        operation_key: 'query_cypher',
        input_schema_ref: 'query_parity_v1',
        validator_key: 'parity_canonical_v1',
        expected: { rows: 4 },
      },
      {
        id: 'compare',
        title: { en: 'Compare canonical sets', ar: 'قارن المجموعات المعيارية' },
        instruction: {
          en: 'Confirm both result sets are equal modulo ordering.',
          ar: 'تأكد أن مجموعتي النتائج متساويتان بغض النظر عن الترتيب.',
        },
        operation_key: 'parity_compare',
        input_schema_ref: 'parity_compare_v1',
        validator_key: 'parity_canonical_v1',
        expected: { equal: true },
      },
    ],
  },
  {
    id: 'critical-dependencies',
    version: '1.1.0',
    module_id: 'graph',
    level: 'intermediate',
    estimated_minutes: 25,
    title: { en: 'Critical Dependencies', ar: 'الاعتماديات الحرجة' },
    description: {
      en: 'Detect the high-impact provider via directed reachability and compare it with naive degree centrality. The two signals are different.',
      ar: 'اكتشف المُوفّر عالي التأثير عبر الوصول الموجّه وقارنه بمؤشر الدرجة البسيط. الإشارتان مختلفتان.',
    },
    technology: ['NetworkX'],
    prerequisites: ['shortest-path'],
    dataset_key: 'dependency-impact-v1',
    required_services: ['postgres'],
    capabilities: ['graph-visualization'],
    public_demo_enabled: true,
    steps: [
      {
        id: 'seed',
        title: { en: 'Load dependency fixture', ar: 'حمّل بيانات الاعتماديات' },
        instruction: {
          en: 'Load the dependency-impact fixture (apps A,B and tools T1,T2,T3).',
          ar: 'حمّل بيانات الأثر (تطبيقات A,B وأدوات T1,T2,T3).',
        },
        operation_key: 'seed_graph',
        input_schema_ref: 'seed_graph_v1',
        validator_key: 'seed_five_nodes_v1',
        expected: { node_count: 5, edge_count: 5 },
      },
      {
        id: 'degree',
        title: { en: 'Score degree', ar: 'احسب الدرجة' },
        instruction: {
          en: 'Inspect in/out degrees and degree centrality for T1.',
          ar: 'افحص درجات الدخول/الخروج ومؤشر الدرجة للأداة T1.',
        },
        operation_key: 'critical_dep_analysis',
        input_schema_ref: 'critical_dep_v1',
        validator_key: 'critical_dep_v1',
        expected: { target: 'T1', impact_set: ['T3'] },
      },
      {
        id: 'reachability',
        title: { en: 'Score reachable dependents', ar: 'احسب التبعيات القابلة للوصول' },
        instruction: {
          en: 'Remove T1 in simulation and confirm T3 becomes unreachable from B.',
          ar: 'احذف T1 في المحاكاة وتأكد أن T3 يصبح غير قابل للوصول من B.',
        },
        operation_key: 'critical_dep_analysis',
        input_schema_ref: 'critical_dep_v1',
        validator_key: 'critical_dep_v1',
        expected: { target: 'T1', impact_set: ['T3'] },
      },
    ],
  },
  {
    id: 'discover-communities',
    version: '1.1.0',
    module_id: 'graph',
    level: 'intermediate',
    estimated_minutes: 25,
    title: { en: 'Discover Communities', ar: 'اكتشاف التجمعات' },
    description: {
      en: 'Apply community detection to a synthetic clustered graph. Provenance must name GDS or NetworkX fallback.',
      ar: 'طبّق اكتشاف التجمعات على رسم مُجمّع صناعياً. يجب أن تُسمّى المصدرية كـ GDS أو بديل NetworkX.',
    },
    technology: ['Neo4j-GDS', 'NetworkX'],
    prerequisites: ['shortest-path'],
    dataset_key: 'communities-v1',
    required_services: ['postgres'],
    capabilities: ['graph-visualization', 'gds-optional'],
    public_demo_enabled: true,
    steps: [
      {
        id: 'seed',
        title: { en: 'Load clustered fixture', ar: 'حمّل بيانات متجمّعة' },
        instruction: {
          en: 'Load the communities fixture (three synthetic clusters).',
          ar: 'حمّل بيانات التجمعات (ثلاث مجموعات صناعية).',
        },
        operation_key: 'seed_graph',
        input_schema_ref: 'seed_graph_v1',
        validator_key: 'communities_seed_v1',
        expected: { node_count: 15 },
      },
      {
        id: 'detect',
        title: { en: 'Run community detection', ar: 'شغّل اكتشاف التجمعات' },
        instruction: {
          en: 'Run Louvain (GDS) or NetworkX fallback.',
          ar: 'شغّل Louvain (GDS) أو بديل NetworkX.',
        },
        operation_key: 'community_detection',
        input_schema_ref: 'community_v1',
        validator_key: 'communities_v1',
        expected: { communities: 3 },
      },
      {
        id: 'provenance',
        title: { en: 'Inspect provenance', ar: 'افحص المصدرية' },
        instruction: {
          en: 'Confirm provenance names GDS or NetworkX fallback.',
          ar: 'تأكد أن المصدرية تُسمّي GDS أو بديل NetworkX.',
        },
        operation_key: 'community_detection',
        input_schema_ref: 'community_v1',
        validator_key: 'communities_provenance_v1',
        expected: { provider: ['gds', 'networkx'] },
      },
    ],
  },
  {
    id: 'trace-one-request',
    version: '1.1.0',
    module_id: 'observability',
    level: 'intermediate',
    estimated_minutes: 25,
    title: { en: 'Trace One Request', ar: 'تتبع طلب واحد' },
    description: {
      en: 'Follow a request through fetch → transform → persist spans. Confirm the trace is correlated with the run record via trace_id.',
      ar: 'تتبّع طلباً عبر فترات fetch ثم transform ثم persist. أكّد أن التتبّع مرتبط بسجل التشغيل عبر trace_id.',
    },
    technology: ['OpenTelemetry', 'Tempo'],
    prerequisites: ['graph-first-network'],
    dataset_key: 'trace-demo-v1',
    required_services: ['postgres'],
    capabilities: ['telemetry'],
    public_demo_enabled: true,
    steps: [
      {
        id: 'start',
        title: { en: 'Start demo', ar: 'ابدأ العرض' },
        instruction: {
          en: "Run the synthetic fetch → transform → persist operation and capture the run's trace_id.",
          ar: 'شغّل العملية الاصطناعية (fetch → transform → persist) والتقط trace_id للتشغيل.',
        },
        operation_key: 'run_trace_demo',
        input_schema_ref: 'trace_demo_v1',
        validator_key: 'trace_demo_v1',
        expected: { span_count: 3 },
      },
      {
        id: 'correlate',
        title: { en: 'Correlate trace_id', ar: 'اربط trace_id' },
        instruction: {
          en: 'Confirm the run record carries the same trace_id as the trace.',
          ar: 'تأكد أن سجل التشغيل يحمل نفس trace_id الخاص بالتتبّع.',
        },
        operation_key: 'run_trace_demo',
        input_schema_ref: 'trace_demo_v1',
        validator_key: 'trace_demo_v1',
        expected: { trace_correlated: true },
      },
    ],
  },
  {
    id: 'build-monitoring-dashboard',
    version: '1.0.0',
    module_id: 'observability',
    level: 'intermediate',
    estimated_minutes: 25,
    title: { en: 'Build Monitoring Dashboard', ar: 'لوحة المراقبة' },
    description: {
      en: 'Observe request rate, error rate and latency over a controlled workload. P50/P95 are computed from histogram buckets.',
      ar: 'راقب معدل الطلبات ومعدل الأخطاء والكمون عبر حمل عمل مضبوط. يُحسب P50/P95 من حدود الهيستوغرام.',
    },
    technology: ['Prometheus', 'Grafana'],
    prerequisites: ['trace-one-request'],
    dataset_key: 'metrics-demo-v1',
    required_services: ['postgres'],
    capabilities: ['telemetry', 'metrics'],
    public_demo_enabled: true,
    steps: [
      {
        id: 'workload',
        title: { en: 'Run controlled workload', ar: 'شغّل حمل عمل مضبوط' },
        instruction: {
          en: 'Run a bounded set of lab operations so the metrics registry has observations.',
          ar: 'شغّل مجموعة محدودة من عمليات المختبر ليصبح لدى سجل المقاييس قراءات.',
        },
        operation_key: 'metrics_demo',
        input_schema_ref: 'metrics_demo_v1',
        validator_key: 'metrics_demo_v1',
        expected: { observations: 50 },
      },
      {
        id: 'dashboard',
        title: { en: 'Inspect P50/P95', ar: 'افحص P50/P95' },
        instruction: {
          en: 'Confirm P50/P95 are computed from histogram buckets.',
          ar: 'تأكد أن P50/P95 يُحسبان من حدود الهيستوغرام.',
        },
        operation_key: 'metrics_demo',
        input_schema_ref: 'metrics_demo_v1',
        validator_key: 'metrics_demo_v1',
        expected: { p95_ms: 200 },
      },
    ],
  },
  {
    id: 'diagnose-hidden-failure',
    version: '1.2.0',
    module_id: 'observability',
    level: 'advanced',
    estimated_minutes: 30,
    title: { en: 'Diagnose a Hidden Failure', ar: 'تشخيص عطل خفي' },
    description: {
      en: 'Inject a bounded failure at a named step, use the trace to find the failing stage, then demonstrate recovery by running the same workflow WITHOUT injection and verify it passes.',
      ar: 'أدخل عطلاً محدوداً في خطوة مسماة، استخدم التتبّع لتحديد المرحلة الفاشلة، ثم اعرض الاسترجاع بتشغيل نفس سير العمل WITHOUT حقن وتحقق من نجاحه.',
    },
    technology: ['OpenTelemetry', 'Grafana'],
    prerequisites: ['trace-one-request', 'build-monitoring-dashboard'],
    dataset_key: 'failure-demo-v1',
    required_services: ['postgres'],
    capabilities: ['telemetry', 'failure-injection'],
    public_demo_enabled: true,
    steps: [
      {
        id: 'inject',
        title: { en: 'Inject failure', ar: 'أدخل العطل' },
        instruction: {
          en: 'Run inject_failure with fail_step=transform. The run must fail with trace_id populated.',
          ar: 'شغّل inject_failure مع fail_step=transform. يجب أن يفشل التشغيل ويكون trace_id معبّأً.',
        },
        operation_key: 'inject_failure',
        input_schema_ref: 'inject_failure_v1',
        validator_key: 'failure_diagnosis_v1',
        expected: { status: 'FAILED', failing_step: 'transform' },
      },
      {
        id: 'diagnose',
        title: { en: 'Diagnose via trace', ar: 'شخّص عبر التتبّع' },
        instruction: {
          en: 'Inspect the trace and identify the failing span.',
          ar: 'افحص التتبّع وحدّد الفترة الفاشلة.',
        },
        operation_key: 'failure_diagnosis',
        input_schema_ref: 'failure_diagnosis_v1',
        validator_key: 'failure_diagnosis_v1',
        expected: { failing_step: 'transform' },
      },
      {
        id: 'recover',
        title: { en: 'Demonstrate recovery', ar: 'اعرض الاسترجاع' },
        instruction: {
          en: 'Re-run the workflow WITHOUT injection and verify it passes.',
          ar: 'أعد تشغيل سير العمل WITHOUT حقن وتحقق من نجاحه.',
        },
        operation_key: 'run_trace_demo',
        input_schema_ref: 'trace_demo_v1',
        validator_key: 'failure_diagnosis_v1',
        expected: { status: 'PASSED' },
      },
    ],
  },
  {
    id: 'integrated-challenge',
    version: '1.2.0',
    module_id: 'challenge',
    level: 'advanced',
    estimated_minutes: 40,
    title: { en: 'Graph and Observability Challenge', ar: 'تحدي الرسم والمراقبة' },
    description: {
      en: 'Identify the faulty dependency and its operational symptom using the graph plus the trace. Then demonstrate recovery by running the same workflow WITHOUT injection and verify it passes.',
      ar: 'حدّد الاعتمادية المعيبة وأعراضها التشغيلية باستخدام الرسم والتتبّع. ثم اعرض الاسترجاع بتشغيل نفس سير العمل WITHOUT حقن وتحقق من نجاحه.',
    },
    technology: ['NetworkX', 'OpenTelemetry', 'Grafana'],
    prerequisites: ['critical-dependencies', 'trace-one-request', 'build-monitoring-dashboard'],
    dataset_key: 'integrated-challenge-v1',
    required_services: ['postgres'],
    capabilities: ['graph-visualization', 'telemetry'],
    public_demo_enabled: true,
    steps: [
      {
        id: 'load',
        title: { en: 'Load integrated dependency graph', ar: 'حمّل رسم الاعتماديات المتكامل' },
        instruction: {
          en: 'Load the integrated dependency fixture (apps, tools and a deliberately failing path).',
          ar: 'حمّل بيانات الاعتماديات المتكاملة (تطبيقات وأدوات ومسار معتلّ متعمّد).',
        },
        operation_key: 'seed_graph',
        input_schema_ref: 'seed_graph_v1',
        validator_key: 'seed_five_nodes_v1',
        expected: { node_count: 7 },
      },
      {
        id: 'identify',
        title: { en: 'Identify faulty dependency', ar: 'حدّد الاعتمادية المعيبة' },
        instruction: {
          en: 'Use graph reachability plus the trace to name the faulty dependency.',
          ar: 'استخدم الوصول عبر الرسم والتتبّع لتسمية الاعتمادية المعيبة.',
        },
        operation_key: 'integrated_diagnosis',
        input_schema_ref: 'integrated_v1',
        validator_key: 'integrated_v1',
        expected: { faulty_node: 'T2' },
      },
      {
        id: 'recover',
        title: { en: 'Demonstrate recovery', ar: 'اعرض الاسترجاع' },
        instruction: {
          en: 'Re-run the workflow WITHOUT injection and verify it passes.',
          ar: 'أعد تشغيل سير العمل WITHOUT حقن وتحقق من نجاحه.',
        },
        operation_key: 'integrated_recovery',
        input_schema_ref: 'integrated_v1',
        validator_key: 'integrated_v1',
        expected: { status: 'PASSED' },
      },
    ],
  },
];

export interface CompactExperiment {
  displayLabel: string;
  id: string;
  title_en: string;
  title_ar: string;
  level: 'beginner' | 'intermediate' | 'advanced';
  minutes: number;
}

/**
 * FALLBACK_EXPERIMENTS_COMPACT — display-only subset used by the Home page
 * preview grid (and any other compact gallery). The displayLabel carries
 * the E0N prefix so the gallery tiles look the same as the live backend
 * output.
 */
export const FALLBACK_EXPERIMENTS_COMPACT: CompactExperiment[] =
  FALLBACK_MANIFESTS.map((m, i) => ({
    displayLabel: `E${String(i + 1).padStart(2, '0')}`,
    id: m.id,
    title_en: m.title.en,
    title_ar: m.title.ar,
    level: m.level,
    minutes: m.estimated_minutes,
  }));
