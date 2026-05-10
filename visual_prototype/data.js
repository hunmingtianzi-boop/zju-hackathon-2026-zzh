// data.js - Externalized Knowledge Graph Data
// In a real scenario, this would be fetched from the Python backend API
const mockElements = {
    nodes: [
        { data: { id: 'n1', label: '发热 (Fever)', type: 'merged', source: '03, 07', size: 60, essence: '体温调定点上移引起的调节性体温升高，是机体的一种防御反应。', reasoning: '整合建议：合并《生理学》与《病理生理学》关于发热的定义。保留《病理生理学》的机制描述，去除《生理学》中重复的基础体温部分，压缩比 25%。' } },
        { data: { id: 'n2', label: '内生致热原 (EP)', type: 'single', source: '07', size: 45, essence: '由产EP细胞在发热激活物的作用下，产生并释放的能引起体温升高的物质。', reasoning: '保留建议：《病理生理学》独有概念，作为发热机制的核心前置条件保留。' } },
        { data: { id: 'n3', label: '体温调节中枢', type: 'merged', source: '01, 03', size: 50, essence: '位于下丘脑视前区-下丘脑前部(POAH)，是体温调节的高级中枢。', reasoning: '整合建议：合并《局部解剖学》关于下丘脑的位置描述与《生理学》的功能描述，形成完整的解剖-功能映射。' } },
        { data: { id: 'n4', label: '致热原性发热', type: 'single', source: '05', size: 40, essence: '由于致热原引起的体温升高，临床上最常见，见于各种感染。', reasoning: '补充建议：《病理学》提供的临床分型，补充理论知识到临床的过渡。' } },
        { data: { id: 'n5', label: '非致热原性发热', type: 'single', source: '05', size: 40, essence: '由体温调节中枢受损、产热异常增多或散热减少引起。', reasoning: '补充建议：与致热原性发热形成并列关系，完善发热的病因分类。' } },
        { data: { id: 'n6', label: '退热药的临床应用', type: 'single', source: '07', size: 35, essence: '通过抑制前列腺素E合成，使调定点回降而发挥退热作用。', reasoning: '应用建议：提取自《病理生理学》发热防治原则，体现知识应用。' } }
    ],
    edges: [
        { data: { source: 'n2', target: 'n3', label: '作用于', type: 'Prerequisite' } },
        { data: { source: 'n3', target: 'n1', label: '导致', type: 'Prerequisite' } },
        { data: { source: 'n4', target: 'n1', label: '属于', type: 'Inclusion' } },
        { data: { source: 'n5', target: 'n1', label: '属于', type: 'Inclusion' } },
        { data: { source: 'n4', target: 'n5', label: '对比', type: 'Parallel' } },
        { data: { source: 'n1', target: 'n6', label: '指导', type: 'Application' } }
    ]
};
