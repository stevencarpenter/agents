// SnowGame.Build.cs
using UnrealBuildTool;
using System.IO;

public class SnowGame : ModuleRules
{
	public SnowGame(ReadOnlyTargetRules Target) : base(Target)
	{
		PCHUsage = PCHUsageMode.NoPCHs;
		CppStandard = CppStandardVersion.Cpp14;
		bUseUnity = false;

		PublicDependencyModuleNames.AddRange(new string[]
		{
			"Core", "CoreUObject", "Engine", "InputCore", "Niagara", "Chaos",
			"PhysicsCore", "RenderCore", "RHI", "UnrealEd", "Slate", "SlateCore"
		});

		PublicIncludePaths.Add("/Users/dev/projects/snow/sim/include");
		PublicIncludePaths.Add(ModuleDirectory);

		// Rust simulation staticlib.
		string Lib = "/Users/dev/projects/snow/sim/target/debug/libsnow_sim.a";
		PublicAdditionalLibraries.Add(Lib);

		if (Target.Platform == UnrealTargetPlatform.Win64)
		{
			PublicSystemLibraries.Add("user32.lib");
		}

		bEnableExceptions = true;
		PublicDefinitions.Add("SNOW_SIM_CHECKS=1");
	}
}
