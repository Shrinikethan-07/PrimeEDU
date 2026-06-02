const EXAM_DATA = {
    "tnpsc-group-1": {
        name: "TNPSC Group I (Prelims & Mains)",
        units: [
            {
                id: "unit-1", name: "General Science",
                chapters: [
                    { id: "u1-c1", name: "Scientific Knowledge & Temper", topics: ["Nature of Universe", "Mechanics", "Matter"] },
                    { id: "u1-c2", name: "Electricity and Magnetism", topics: ["Electronics", "Communication", "Acoustics"] }
                ]
            },
            {
                id: "unit-8", name: "History & Culture of Tamil Nadu",
                chapters: [
                    { id: "u8-c1", name: "History of Tamil Society", topics: ["Archaeological discoveries", "Sangam Age Literature"] },
                    { id: "u8-c2", name: "Socio-Political Movements", topics: ["Self Respect Movement", "Justice Party", "Dravidian Movement"] }
                ]
            }
        ]
    },
    "neet-ug": {
        name: "NEET UG (Medical Entrance)",
        units: [
            {
                id: "physics", name: "Physics",
                chapters: [
                    { id: "p-c1", name: "Mechanics", topics: ["Kinematics", "Laws of Motion", "Work, Energy & Power"] },
                    { id: "p-c2", name: "Electrodynamics", topics: ["Electrostatics", "Current Electricity", "Magnetic Effects"] }
                ]
            },
            {
                id: "biology", name: "Biology",
                chapters: [
                    { id: "b-c1", name: "Human Physiology", topics: ["Digestion", "Breathing", "Body Fluids", "Excretion"] },
                    { id: "b-c2", name: "Genetics & Evolution", topics: ["Inheritance", "Molecular Basis", "Evolution"] }
                ]
            }
        ]
    },
    "jee-main": {
        name: "JEE Main & Advanced",
        units: [
            {
                id: "math", name: "Mathematics",
                chapters: [
                    { id: "m-c1", name: "Calculus", topics: ["Limits & Continuity", "Differentiation", "Integration", "Differential Equations"] },
                    { id: "m-c2", name: "Algebra", topics: ["Matrices", "Probability", "Complex Numbers"] }
                ]
            }
        ]
    },
    "upsc-cse": {
        name: "UPSC Civil Services",
        units: [
            {
                id: "prelims-gs", name: "Prelims Paper I (GS)",
                chapters: [
                    { id: "gs-c1", name: "Indian Polity", topics: ["Constitution", "Preamble", "Fundamental Rights", "Parliament"] },
                    { id: "gs-c2", name: "Economy", topics: ["Banking", "Inflation", "Fiscal Policy", "Agriculture"] }
                ]
            }
        ]
    },
    "neet-pg": {
        name: "NEET PG (Medical Specialities)",
        units: [
            {
                id: "pre-clinical", name: "Pre-Clinical", chapters: [
                    { id: "ana", name: "Anatomy", topics: ["Gross Anatomy", "Embryology", "Histology"] },
                    { id: "phys", name: "Physiology", topics: ["General Physiology", "Hematology", "Nerve-Muscle"] },
                    { id: "bio", name: "Biochemistry", topics: ["Metabolism", "Molecular Biology", "Nutrition"] }
                ]
            },
            {
                id: "para-clinical", name: "Para-Clinical", chapters: [
                    { id: "path", name: "Pathology", topics: ["General Pathology", "Systemic Pathology", "Hematology"] },
                    { id: "pharm", name: "Pharmacology", topics: ["General Pharm", "ANS", "CNS", "CVS", "Antibiotics"] },
                    { id: "micro", name: "Microbiology", topics: ["Bacteriology", "Virology", "Immunology"] }
                ]
            },
            {
                id: "clinical", name: "Clinical", chapters: [
                    { id: "med", name: "Medicine", topics: ["Cardiology", "Neurology", "Gastroenterology"] },
                    { id: "surg", name: "Surgery", topics: ["General Surgery", "Urology", "Orthopaedics"] },
                    { id: "obg", name: "OBG", topics: ["Obstetrics", "Gynaecology"] }
                ]
            }
        ]
    },
    "ca-track": {
        name: "Chartered Accountancy (Complete)",
        units: [
            {
                id: "foundation", name: "CA Foundation", chapters: [
                    { id: "acc", name: "Accounting", topics: ["Brs", "Inventory", "Depreciation", "Final Accounts"] },
                    { id: "law", name: "Business Law", topics: ["Contract Act", "Sale of Goods", "Partnership"] }
                ]
            },
            {
                id: "intermediate", name: "CA Intermediate", chapters: [
                    { id: "tax", name: "Taxation", topics: ["Income Tax", "GST"] },
                    { id: "audit", name: "Auditing", topics: ["Audit Plan", "Internal Control"] }
                ]
            },
            {
                id: "final", name: "CA Final", chapters: [
                    { id: "fr", name: "Financial Reporting", topics: ["Ind AS", "Consolidation", "Valuation"] },
                    { id: "scm", name: "Strategic Cost Management", topics: ["Standard Costing", "Pricing Decisions"] }
                ]
            }
        ]
    }
};

if (typeof module !== 'undefined') { module.exports = EXAM_DATA; }
