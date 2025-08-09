
using Microsoft.Build.Locator;
using Microsoft.CodeAnalysis.MSBuild;
using Microsoft.CodeAnalysis.CSharp;
using Microsoft.CodeAnalysis.CSharp.Syntax;
using Newtonsoft.Json;

namespace SolutionAnalyzer
{
    class SemanticInfo
    {
        public string Project { get; set; }
        public string File { get; set; }
        public List<string> Classes { get; set; } = new List<string>();
        public List<string> Methods { get; set; } = new List<string>();
        public List<string> Comments { get; set; } = new List<string>();
    }
    internal class Program
    {
        static async System.Threading.Tasks.Task Main(string[] args)
        {
            if (args.Length < 1)
            {
                Console.WriteLine("Usage: SolutionAnalyzer <solution.sln>");
                return;
            }
            MSBuildLocator.RegisterDefaults();

            var workspace = MSBuildWorkspace.Create();
            var solution = await workspace.OpenSolutionAsync(args[0]);
            var result = new List<SemanticInfo>();

            foreach (var project in solution.Projects)
                foreach (var doc in project.Documents)
                {
                    var info = new SemanticInfo { Project = project.Name, File = doc.Name };
                    var text = await doc.GetTextAsync();
                    var tree = CSharpSyntaxTree.ParseText(text.ToString());
                    var root = await tree.GetRootAsync();

                    // Classes
                    var classes = root.DescendantNodes().OfType<ClassDeclarationSyntax>();
                    foreach (var c in classes)
                    {
                        info.Classes.Add(c.Identifier.Text);

                        // XML comments
                        if (c.GetLeadingTrivia().ToString().Contains("///"))
                            info.Comments.Add(c.GetLeadingTrivia().ToString().Trim());
                    }

                    // Methods
                    var methods = root.DescendantNodes().OfType<MethodDeclarationSyntax>();
                    foreach (var m in methods)
                    {
                        info.Methods.Add(m.Identifier.Text);

                        if (m.GetLeadingTrivia().ToString().Contains("///"))
                            info.Comments.Add(m.GetLeadingTrivia().ToString().Trim());
                    }
                    // If file has info
                    if (info.Classes.Count + info.Methods.Count + info.Comments.Count > 0)
                        result.Add(info);
                }
            File.WriteAllText("semantic_summary.json", JsonConvert.SerializeObject(result, Formatting.Indented));
            Console.WriteLine("Extracted semantic info to semantic_summary.json");
        }
    }
}
